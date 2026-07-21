"""Capability matrix, controller topology, USB2 fallback, and the D-12 registry.

The matrix builder and the topology computers run fully on descriptor fixtures. The
*live* detection of these facts from a real bus is the deferred half (①②③); here the
logic that consumes an enumeration is proven, and the reverify hook re-runs it on real
descriptors. The registry check encodes `16` D-12: required/optional named slots, not a
rigid five-stream schema.
"""

from __future__ import annotations

from backend.camera import fixtures
from backend.camera.descriptor import StreamKind
from backend.camera.matrix import (
    CapabilityRequirement,
    build_matrix,
    check_capability_registry,
    controller_membership,
    shared_controller_warnings,
    usb2_fallback_serials,
)


def test_matrix_row_carries_the_spec_columns() -> None:
    """Each row is {serial, type, model, profiles[], controller, link speed} (FR-CAM-002)."""
    rows = build_matrix([fixtures.realsense_rgbd(), fixtures.webcam_720p()])
    by_serial = {r.serial: r for r in rows}
    rs = by_serial["rs-0001"]
    assert rs.camera_type == "intelrealsense"
    assert rs.model == "Intel RealSense D435"
    assert rs.controller == "usb-controller-0"
    assert rs.link_speed == "usb3"
    assert (640, 480, 30, "rgb") in rs.profiles
    assert (640, 480, 30, "depth") in rs.profiles


def test_shared_controller_raises_a_warning() -> None:
    """Two cameras on one controller warn about the shared link (FR-CAM-005)."""
    pair = list(fixtures.same_controller_pair())
    membership = controller_membership(pair)
    assert membership["usb-controller-shared"] == ("rs-share-a", "rs-share-b")
    warnings = shared_controller_warnings(pair)
    assert len(warnings) == 1
    assert "usb-controller-shared" in warnings[0]


def test_distinct_controllers_raise_no_warning() -> None:
    """Cameras on separate controllers do not warn."""
    assert shared_controller_warnings([fixtures.realsense_rgbd(), fixtures.webcam_720p()]) == ()


def test_usb2_fallback_is_flagged() -> None:
    """A camera on a USB2 link is surfaced as the FR-CAM-003 fallback."""
    cams = [fixtures.realsense_rgbd(), fixtures.usb2_fallback_webcam()]
    assert usb2_fallback_serials(cams) == ("uvc-fallback-480",)


def test_registry_required_subset_is_satisfied() -> None:
    """A required RGB slot plus an optional depth slot: present required => satisfied (D-12)."""
    bound = {"wrist_rgb": fixtures.webcam_720p(), "scene_depth": fixtures.realsense_rgbd()}
    requirements = [
        CapabilityRequirement("wrist_rgb", required=True, needs=frozenset({StreamKind.RGB})),
        CapabilityRequirement("scene_depth", required=False, needs=frozenset({StreamKind.DEPTH})),
    ]
    check = check_capability_registry(bound, requirements)
    assert check.satisfied
    assert check.missing_required == ()
    assert check.present_optional == ("scene_depth",)


def test_registry_missing_required_slot_is_unsatisfied() -> None:
    """A required slot with no bound camera fails, naming the gap (not a rigid schema)."""
    requirements = [
        CapabilityRequirement("wrist_rgb", required=True, needs=frozenset({StreamKind.RGB})),
    ]
    check = check_capability_registry({}, requirements)
    assert not check.satisfied
    assert check.missing_required == ("wrist_rgb",)


def test_registry_required_slot_missing_a_stream_kind_fails() -> None:
    """A slot present but not providing its required depth stream is under-provisioned."""
    bound = {"scene_depth": fixtures.webcam_720p()}  # RGB only, no depth
    requirements = [
        CapabilityRequirement("scene_depth", required=True, needs=frozenset({StreamKind.DEPTH})),
    ]
    check = check_capability_registry(bound, requirements)
    assert check.missing_required == ("scene_depth",)


def test_extra_cameras_are_reported_not_rejected() -> None:
    """Unregistered slots are allowed (own namespace), only reported (D-12)."""
    bound = {"wrist_rgb": fixtures.webcam_720p(), "bonus": fixtures.realsense_rgbd()}
    requirements = [
        CapabilityRequirement("wrist_rgb", required=True, needs=frozenset({StreamKind.RGB})),
    ]
    check = check_capability_registry(bound, requirements)
    assert check.satisfied
    assert check.unexpected == ("bonus",)
