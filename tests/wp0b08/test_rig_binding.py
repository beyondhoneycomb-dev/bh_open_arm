"""Which camera is in which slot is read from the operator's record, never from the source.

The three port strings that used to sit in `cli.RIG_SLOTS` were the answer on the day they were
typed. Nothing checked them afterwards, and the failure they produce is silent: the wrist pair
looks alike, so a left slot pointed at the right camera is invisible in the footage and shows up
much later as a policy that reaches the wrong way.

What replaces them is the shape `ops/hw/canbind` already uses for the two arms — enumerate what
is present, resolve against a persisted identification, and refuse rather than guess.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.camera.portpath import CaptureNode
from backend.camera.rig import (
    BINDING_VERSION,
    CameraBinding,
    CameraBindingError,
    binding_path,
    check_binding,
    load_binding,
    resolve_slots,
    save_binding,
)

SLOTS = ("wrist_left", "wrist_right", "scene_stereo")

# Two wrist cameras that report the same card and the same serial, which is this rig's actual
# situation and the reason the port is the only axis that separates them.
WRIST_CARD = "Arducam B0495 (USB3 2.3MP)"
LEFT_PORT = "usb-0000:00:0d.0-1.1.1"
RIGHT_PORT = "usb-0000:00:0d.0-1.1.3.4"
STEREO_PORT = "usb-0000:80:14.0-4.1"


def _node(device: str, port: str, card: str) -> CaptureNode:
    """Build a capture node without touching a device."""
    return CaptureNode(device=Path(device), port_path=port, card=card)


PRESENT = (
    _node("/dev/video0", STEREO_PORT, "ZED-M: ZED-M"),
    _node("/dev/video2", LEFT_PORT, WRIST_CARD),
    _node("/dev/video4", RIGHT_PORT, WRIST_CARD),
)

BOUND = CameraBinding(
    slots={"wrist_left": LEFT_PORT, "wrist_right": RIGHT_PORT, "scene_stereo": STEREO_PORT}
)


def test_a_slot_resolves_to_whatever_node_holds_its_port_now() -> None:
    """The device number is not the identity: `/dev/videoN` renumbers, the port does not.

    Two cameras that report one card and one serial are separated here by nothing but the port,
    which is the whole reason the record keys on it.
    """
    resolved = resolve_slots(BOUND, SLOTS, PRESENT)

    assert resolved["wrist_left"].device == Path("/dev/video2")
    assert resolved["wrist_right"].device == Path("/dev/video4")
    assert resolved["scene_stereo"].device == Path("/dev/video0")


def test_the_same_record_follows_a_camera_that_renumbered() -> None:
    """A reboot that swaps device numbers must not swap the arms' wrist views.

    Same ports, different nodes. This is the failure the port key exists for, and it has been
    observed on this bench — the ZED-M and an Arducam have traded numbers with both plugs untouched.
    """
    renumbered = (
        _node("/dev/video4", STEREO_PORT, "ZED-M: ZED-M"),
        _node("/dev/video0", LEFT_PORT, WRIST_CARD),
        _node("/dev/video2", RIGHT_PORT, WRIST_CARD),
    )

    resolved = resolve_slots(BOUND, SLOTS, renumbered)

    assert resolved["wrist_left"].device == Path("/dev/video0")
    assert resolved["wrist_right"].device == Path("/dev/video2")


def test_a_slot_whose_camera_is_gone_is_refused_not_skipped() -> None:
    """`PG-CAM-001` measures this set; a run over two of three answers a question nobody asked.

    The refusal names both halves — the slot that went missing and the ports present that nothing
    claims — because a camera moved to another port produces both at once, and reporting only the
    first sends the operator hunting a dead camera that is plugged in and working.
    """
    moved = (
        _node("/dev/video0", STEREO_PORT, "ZED-M: ZED-M"),
        _node("/dev/video2", LEFT_PORT, WRIST_CARD),
        _node("/dev/video4", "usb-0000:00:0d.0-1.1.3.3", WRIST_CARD),
    )

    with pytest.raises(CameraBindingError) as refusal:
        resolve_slots(BOUND, SLOTS, moved)

    assert "wrist_right" in str(refusal.value)
    assert "usb-0000:00:0d.0-1.1.3.3" in str(refusal.value)


def test_a_check_reports_both_halves_without_raising() -> None:
    """The bind flow shows the whole picture at once, so it reads rather than catches."""
    partial = (_node("/dev/video0", STEREO_PORT, "ZED-M: ZED-M"),)

    check = check_binding(BOUND, SLOTS, partial)

    assert check.ok is False
    assert check.missing == ("wrist_left", "wrist_right")
    assert set(check.resolved) == {"scene_stereo"}


def test_an_unclaimed_camera_is_reported_and_is_not_a_failure() -> None:
    """A fourth camera plugged into this host is not this rig's problem, but it is worth naming."""
    extra = (*PRESENT, _node("/dev/video6", "usb-0000:00:14.0-2", "Some Webcam"))

    check = check_binding(BOUND, SLOTS, extra)

    assert check.ok is True
    assert check.unbound_ports == ("usb-0000:00:14.0-2",)


def test_a_record_survives_a_write_and_a_read(tmp_path: Path) -> None:
    """The round trip, so a save that wrote a shape the loader refuses fails here not on the rig."""
    path = binding_path(tmp_path)

    save_binding(path, BOUND)

    assert load_binding(path).slots == BOUND.slots


def test_a_missing_record_names_the_command_that_writes_one(tmp_path: Path) -> None:
    """An operator who reads this refusal has to know what to run next."""
    with pytest.raises(CameraBindingError, match="S-06"):
        load_binding(binding_path(tmp_path))


def test_a_record_from_a_future_shape_is_refused_rather_than_read_as_empty(tmp_path: Path) -> None:
    """An unknown version with no slots would read as a rig with no cameras, which is not a rig."""
    path = binding_path(tmp_path)
    path.write_text(json.dumps({"version": BINDING_VERSION + 1, "slots": {}}), encoding="utf-8")

    with pytest.raises(CameraBindingError, match="version"):
        load_binding(path)


@pytest.mark.parametrize(
    "document",
    [
        pytest.param({"version": BINDING_VERSION, "slots": []}, id="slots_not_a_map"),
        pytest.param({"version": BINDING_VERSION, "slots": {"wrist_left": ""}}, id="empty_port"),
        pytest.param({"version": BINDING_VERSION, "slots": {"wrist_left": 2}}, id="port_is_an_int"),
    ],
)
def test_a_malformed_record_is_refused(tmp_path: Path, document: dict[str, object]) -> None:
    """A port that is a number is an enumeration index wearing a port's name (`06` FR-CAM-004)."""
    path = binding_path(tmp_path)
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(CameraBindingError, match="slot-to-port"):
        load_binding(path)
