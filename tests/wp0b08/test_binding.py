"""Acceptance ⑧ — serial-based slot binding, index-based binding rejected (FR-CAM-004).

The contract is a hard gate: a slot binds by a stable serial or a udev by-id symlink,
never by an enumeration index. Every index shape (an int, a bare-integer string, a
`/dev/videoN` node) is refused; a symlink and a real serial are accepted and resolve.
"""

from __future__ import annotations

import pytest

from backend.camera import fixtures
from backend.camera.binding import (
    BindingError,
    IndexBindingError,
    parse_binding_spec,
    resolve_bindings,
)


def test_serial_spec_parses_and_sorts() -> None:
    """A serial-keyed spec parses into bindings, sorted by slot."""
    bindings = parse_binding_spec(fixtures.serial_based_binding_spec())
    assert [b.slot for b in bindings] == ["fallback", "front", "wrist"]
    assert {b.serial for b in bindings} == {"rs-0001", "uvc-logitech-720", "uvc-fallback-480"}


def test_udev_symlink_is_accepted_not_treated_as_index() -> None:
    """A `/dev/v4l/by-id/...` symlink is stable identity, so it must pass (FR-CAM-004)."""
    bindings = parse_binding_spec(fixtures.udev_symlink_binding_spec())
    assert bindings[0].serial.startswith("/dev/v4l/by-id/")


@pytest.mark.parametrize(
    "value",
    [0, 3, "0", "12", "/dev/video0", "/dev/video2"],
    ids=["int-zero", "int", "bare-str-zero", "bare-str", "node-zero", "node"],
)
def test_index_based_binding_is_rejected(value: object) -> None:
    """Every enumeration-index shape is refused before it can pin a moving slot (⑧)."""
    with pytest.raises(IndexBindingError):
        parse_binding_spec({"wrist": value})


def test_whole_index_fixture_is_rejected() -> None:
    """The index-based fixture spec is rejected as a whole (⑧)."""
    with pytest.raises(IndexBindingError):
        parse_binding_spec(fixtures.index_based_binding_spec())


def test_empty_serial_is_rejected() -> None:
    """A blank serial is malformed, distinct from an index error."""
    with pytest.raises(BindingError):
        parse_binding_spec({"wrist": "   "})


def test_resolution_matches_descriptors_by_serial() -> None:
    """Validated bindings resolve to the enumerated descriptors that carry the serials."""
    descriptors = [
        fixtures.realsense_rgbd(),
        fixtures.webcam_720p(),
        fixtures.usb2_fallback_webcam(),
    ]
    bindings = parse_binding_spec(fixtures.serial_based_binding_spec())
    resolved = resolve_bindings(bindings, descriptors)
    assert resolved["wrist"].serial == "rs-0001"
    assert resolved["front"].serial == "uvc-logitech-720"
    assert resolved["fallback"].serial == "uvc-fallback-480"


def test_unknown_serial_does_not_resolve() -> None:
    """A serial that matches no enumerated camera is an error, not a silent drop."""
    bindings = parse_binding_spec({"wrist": "not-attached"})
    with pytest.raises(BindingError, match="no enumerated camera"):
        resolve_bindings(bindings, [fixtures.realsense_rgbd()])
