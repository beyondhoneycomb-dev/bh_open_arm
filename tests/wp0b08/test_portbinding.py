"""Slot-to-camera binding by port, and the refusals that keep it from following the wrong one.

Every case states its cameras rather than probing, because what is under test is what the
binding does when a port went missing, duplicated, or was never bound — none of which a host
with correctly plugged cameras can show.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.camera.portbinding import (
    BINDING_FILENAME,
    BINDING_VERSION,
    FIELD_SLOTS,
    FIELD_VERSION,
    CameraBinding,
    CameraBindingError,
    binding_from_document,
    binding_path,
    check_binding,
    load_binding,
    save_binding,
)
from backend.camera.portpath import AmbiguousCameraPortError, CaptureNode

WRIST_LEFT_SLOT = "wrist_left"
WRIST_RIGHT_SLOT = "wrist_right"
SCENE_SLOT = "scene"

WRIST_LEFT_PORT = "usb-0000:00:0d.0-1.1.3.3"
WRIST_RIGHT_PORT = "usb-0000:00:0d.0-1.1.4"
SCENE_PORT = "usb-0000:80:14.0-4.1"

ARDUCAM_CARD = "Arducam B0495 (USB3 2.3MP)"

# The node number the same camera takes on a later boot. Different from the one it was bound on,
# which is the point: the binding must resolve through the port, not the number.
RENUMBERED_NODE = "/dev/video7"


def _node(device: str, port: str, card: str = ARDUCAM_CARD) -> CaptureNode:
    """One capture node, stated rather than probed."""
    return CaptureNode(device=Path(device), port_path=port, card=card)


def _wrist_pair() -> CameraBinding:
    """Both wrists bound to the ports they were confirmed on."""
    return CameraBinding(
        slots={WRIST_LEFT_SLOT: WRIST_LEFT_PORT, WRIST_RIGHT_SLOT: WRIST_RIGHT_PORT}
    )


def test_a_bound_slot_opens_the_camera_on_its_port() -> None:
    left = _node("/dev/video0", WRIST_LEFT_PORT)
    right = _node("/dev/video2", WRIST_RIGHT_PORT)

    assert _wrist_pair().node_for(WRIST_RIGHT_SLOT, (left, right)) is right


def test_a_renumbered_node_still_resolves_through_its_port() -> None:
    """`/dev/videoN` moves between boots; the port is what the slot was bound to."""
    right = _node(RENUMBERED_NODE, WRIST_RIGHT_PORT)

    resolved = _wrist_pair().node_for(
        WRIST_RIGHT_SLOT, (_node("/dev/video3", WRIST_LEFT_PORT), right)
    )

    assert resolved.device == Path(RENUMBERED_NODE)


def test_an_unbound_slot_is_refused_rather_than_given_the_first_camera() -> None:
    present = (_node("/dev/video0", WRIST_LEFT_PORT), _node("/dev/video2", WRIST_RIGHT_PORT))

    with pytest.raises(CameraBindingError, match="has no bound camera"):
        _wrist_pair().node_for(SCENE_SLOT, present)


def test_a_slot_whose_camera_moved_is_refused_rather_than_re_resolved() -> None:
    """The camera on the other port is a camera. It is not this slot's camera."""
    present = (_node("/dev/video0", WRIST_LEFT_PORT),)

    with pytest.raises(CameraBindingError, match="carries no camera now"):
        _wrist_pair().node_for(WRIST_RIGHT_SLOT, present)


def test_resolving_against_two_cameras_on_one_port_is_refused() -> None:
    present = (_node("/dev/video0", WRIST_LEFT_PORT), _node("/dev/video2", WRIST_LEFT_PORT))

    with pytest.raises(AmbiguousCameraPortError):
        _wrist_pair().node_for(WRIST_LEFT_SLOT, present)


def test_a_check_reports_what_resolved_what_is_missing_and_what_is_unclaimed() -> None:
    present = (_node("/dev/video0", WRIST_LEFT_PORT), _node("/dev/video4", SCENE_PORT, "ZED-M"))

    check = check_binding(_wrist_pair(), present)

    assert set(check.resolved) == {WRIST_LEFT_SLOT}
    assert check.missing == (WRIST_RIGHT_SLOT,)
    assert check.unbound_ports == (SCENE_PORT,)
    assert check.ok is False


def test_a_check_with_every_slot_present_is_ok_even_with_a_spare_camera() -> None:
    present = (
        _node("/dev/video0", WRIST_LEFT_PORT),
        _node("/dev/video2", WRIST_RIGHT_PORT),
        _node("/dev/video4", SCENE_PORT, "ZED-M"),
    )

    check = check_binding(_wrist_pair(), present)

    assert check.ok is True
    assert check.unbound_ports == (SCENE_PORT,)


def test_a_slot_bound_to_an_index_is_refused() -> None:
    """An int is the enumeration index FR-CAM-004 refuses; coercing it would hide that."""
    document = {FIELD_VERSION: BINDING_VERSION, FIELD_SLOTS: {WRIST_LEFT_SLOT: 0}}

    with pytest.raises(CameraBindingError, match="not a port path"):
        binding_from_document(document)


def test_a_slot_bound_to_a_blank_string_is_refused() -> None:
    document = {FIELD_VERSION: BINDING_VERSION, FIELD_SLOTS: {WRIST_LEFT_SLOT: "   "}}

    with pytest.raises(CameraBindingError, match="not a port path"):
        binding_from_document(document)


def test_a_binding_from_a_different_version_is_refused() -> None:
    document = {FIELD_VERSION: BINDING_VERSION + 1, FIELD_SLOTS: {WRIST_LEFT_SLOT: WRIST_LEFT_PORT}}

    with pytest.raises(CameraBindingError, match="version"):
        binding_from_document(document)


def test_a_document_with_no_slot_map_is_refused() -> None:
    with pytest.raises(CameraBindingError, match=FIELD_SLOTS):
        binding_from_document({FIELD_VERSION: BINDING_VERSION})


def test_a_saved_binding_reads_back_as_the_same_answer(tmp_path: Path) -> None:
    path = binding_path(tmp_path)

    save_binding(path, _wrist_pair())

    assert path.name == BINDING_FILENAME
    assert load_binding(path) == _wrist_pair()


def test_no_binding_file_reads_as_never_bound(tmp_path: Path) -> None:
    assert load_binding(binding_path(tmp_path)) is None


def test_a_corrupt_binding_is_refused_rather_than_read_as_never_bound(tmp_path: Path) -> None:
    """ "Absent" prompts a rebind; "corrupt" means something already went wrong."""
    path = binding_path(tmp_path)
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(CameraBindingError, match="cannot be read"):
        load_binding(path)


def test_the_written_document_carries_its_version(tmp_path: Path) -> None:
    """A record with no version cannot be refused by the next schema change."""
    path = binding_path(tmp_path)

    save_binding(path, _wrist_pair())

    assert json.loads(path.read_text(encoding="utf-8"))[FIELD_VERSION] == BINDING_VERSION
