"""Port-based camera identity, for the pair whose serials are the same string.

Every case here runs over a node list rather than `/dev`, because the property under test is
what the binding does with an ambiguous or missing port — and a host that happens to have two
distinguishable cameras plugged in cannot show either.

The real-hardware half is `test_the_bench_cameras_are_told_apart_by_port`, which skips when
nothing is plugged in. It is what proves the ioctl reads what this module thinks it reads;
the rest would pass over a constant.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.camera.portpath import (
    V4L2_CAP_VIDEO_CAPTURE,
    AmbiguousCameraPortError,
    CameraPortError,
    CaptureNode,
    assert_ports_distinguish,
    discovery_rows,
    enumerate_capture_nodes,
    node_by_port,
    video_device_nodes,
)

# Two ports off one controller, as the wrist pair sits on this rig.
WRIST_LEFT_PORT = "usb-0000:00:0d.0-1.1.3.3"
WRIST_RIGHT_PORT = "usb-0000:00:0d.0-1.1.4"

# The name both wrist cameras report, and the serial they share. The card string cannot
# separate them, which is the whole reason this module exists.
ARDUCAM_CARD = "Arducam B0495 (USB3 2.3MP)"

# How many cameras the bench carries when the real check runs: two wrists and the ZED.
BENCH_CAMERA_COUNT = 3


def _node(device: str, port: str, card: str = ARDUCAM_CARD) -> CaptureNode:
    """One capture node, stated rather than probed."""
    return CaptureNode(device=Path(device), port_path=port, card=card)


def test_two_cameras_on_two_ports_are_distinguished() -> None:
    nodes = (_node("/dev/video0", WRIST_LEFT_PORT), _node("/dev/video2", WRIST_RIGHT_PORT))

    assert_ports_distinguish(nodes)


def test_two_cameras_reporting_one_port_are_refused() -> None:
    """A port carrying two nodes resolves to whichever enumerated first — an index in disguise."""
    nodes = (_node("/dev/video0", WRIST_LEFT_PORT), _node("/dev/video2", WRIST_LEFT_PORT))

    with pytest.raises(AmbiguousCameraPortError, match=WRIST_LEFT_PORT):
        assert_ports_distinguish(nodes)


def test_one_camera_alone_is_not_called_ambiguous() -> None:
    """A single camera has nothing to be confused with; the refusal is about collision only."""
    assert_ports_distinguish((_node("/dev/video0", WRIST_LEFT_PORT),))


def test_an_empty_bench_is_not_called_ambiguous() -> None:
    assert_ports_distinguish(())


def test_a_bound_port_resolves_to_the_node_on_it() -> None:
    left = _node("/dev/video0", WRIST_LEFT_PORT)
    right = _node("/dev/video2", WRIST_RIGHT_PORT)

    assert node_by_port((left, right), WRIST_RIGHT_PORT) is right


def test_a_port_with_nothing_on_it_is_refused_rather_than_substituted() -> None:
    """The camera moved. Opening the other one would stream the wrong arm into the slot."""
    present = (_node("/dev/video0", WRIST_LEFT_PORT),)

    with pytest.raises(CameraPortError, match="no capture node is on port"):
        node_by_port(present, WRIST_RIGHT_PORT)


def test_a_lookup_over_an_ambiguous_set_is_refused_before_it_picks_one() -> None:
    """The collision is refused even when the asked-for port is the duplicated one."""
    nodes = (_node("/dev/video0", WRIST_LEFT_PORT), _node("/dev/video2", WRIST_LEFT_PORT))

    with pytest.raises(AmbiguousCameraPortError):
        node_by_port(nodes, WRIST_LEFT_PORT)


def test_nodes_are_ordered_by_number_and_not_by_filesystem_order(tmp_path: Path) -> None:
    """`video10` sorts after `video2`; a plain string sort puts it between `video1` and `video2`."""
    for name in ("video10", "video2", "video1"):
        (tmp_path / name).touch()

    assert [node.name for node in video_device_nodes(tmp_path)] == ["video1", "video2", "video10"]


def test_a_device_root_holding_no_video_node_enumerates_nothing(tmp_path: Path) -> None:
    (tmp_path / "ttyUSB0").touch()

    assert enumerate_capture_nodes(tmp_path) == ()


def test_a_node_that_cannot_be_opened_is_dropped_rather_than_guessed(tmp_path: Path) -> None:
    """A regular file is not a video node; the probe must not report it as a camera."""
    (tmp_path / "video0").write_text("not a device", encoding="utf-8")

    assert enumerate_capture_nodes(tmp_path) == ()


def test_the_capture_flag_is_the_bit_the_kernel_defines() -> None:
    """Pinned because a wrong bit would read metadata nodes as cameras and double the count."""
    assert V4L2_CAP_VIDEO_CAPTURE == 0x00000001


@pytest.mark.skipif(
    len(enumerate_capture_nodes()) < BENCH_CAMERA_COUNT,
    reason=(
        "the wrist pair and the ZED, told apart by the port the kernel reports: requires all "
        "three cameras plugged in"
    ),
)
def test_the_bench_cameras_are_told_apart_by_port() -> None:
    """The ioctl half: what `QUERYCAP` answers on this host, over the cameras actually fitted.

    Asserts the separation rather than the count. Three nodes that all reported one port would
    satisfy a count and leave every slot bound to the same camera.
    """
    nodes = enumerate_capture_nodes()

    assert_ports_distinguish(nodes)
    assert len({node.port_path for node in nodes}) == len(nodes)
    assert all(node.port_path for node in nodes), "a node reported an empty port"
    assert len({node.card for node in nodes}) < len(nodes), (
        "the cards on this bench are all distinct, so this case is no longer covering the "
        "collision it was written for"
    )


def test_discovery_rows_lead_with_the_port_the_screen_assigns_against() -> None:
    """The card repeats across the wrist pair; the port is what a row is picked by."""
    nodes = (_node("/dev/video2", WRIST_RIGHT_PORT), _node("/dev/video0", WRIST_LEFT_PORT))

    rows = discovery_rows(nodes)

    assert [row["port_path"] for row in rows] == [WRIST_LEFT_PORT, WRIST_RIGHT_PORT]
    assert {row["card"] for row in rows} == {ARDUCAM_CARD}


def test_discovery_rows_are_ordered_so_the_screen_list_does_not_reshuffle() -> None:
    """Enumeration order follows the device numbers, which move; the rows must not."""
    forward = discovery_rows(
        (_node("/dev/video0", WRIST_LEFT_PORT), _node("/dev/video2", WRIST_RIGHT_PORT))
    )
    reversed_order = discovery_rows(
        (_node("/dev/video2", WRIST_RIGHT_PORT), _node("/dev/video0", WRIST_LEFT_PORT))
    )

    assert forward == reversed_order


def test_discovery_over_two_cameras_on_one_port_is_refused() -> None:
    nodes = (_node("/dev/video0", WRIST_LEFT_PORT), _node("/dev/video2", WRIST_LEFT_PORT))

    with pytest.raises(AmbiguousCameraPortError):
        discovery_rows(nodes)
