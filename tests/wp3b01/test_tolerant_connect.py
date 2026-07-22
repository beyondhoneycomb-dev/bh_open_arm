"""Acceptance ① (CG-3B-01a) — a dead camera is warned and skipped; the arm proceeds.

`FR-CAM-084`: killing one camera must not fail the arm's connect or motion. The other
cameras open, the dead one is skipped with a warning and an `OA-CAM-001` envelope, and
the report's `arm_may_proceed` stays true with no blocking failure.
"""

from __future__ import annotations

import pytest

from backend.camera import fixtures as camfx
from backend.camera.binding import BindingError, IndexBindingError
from backend.sensing.connect import ConnectStatus, SkipReason, tolerant_connect
from contracts.prim import codes
from tests.wp3b01._support import RaisingProbe, dead_camera, live_camera, registry_with


def _three_camera_binding() -> dict[str, object]:
    return {"wrist": "rs-0001", "front": "uvc-logitech-720", "fallback": "uvc-fallback-480"}


def _three_descriptors() -> list:
    return [camfx.realsense_rgbd(), camfx.webcam_720p(), camfx.usb2_fallback_webcam()]


def test_dead_camera_is_skipped_and_arm_proceeds() -> None:
    """One dead camera → warned + skipped; the others open and the arm is not blocked."""
    registry = registry_with("wrist", "front", "fallback")
    probes = {
        "wrist": live_camera("wrist"),
        "front": dead_camera("front"),
        "fallback": live_camera("fallback"),
    }
    report = tolerant_connect(registry, _three_camera_binding(), _three_descriptors(), probes)

    assert report.arm_may_proceed is True
    assert report.blocking_failures == ()
    assert {o.slot for o in report.opened} == {"wrist", "fallback"}

    front = report.by_slot("front")
    assert front.status is ConnectStatus.SKIPPED
    assert front.reason is SkipReason.NO_FRAME
    assert front.error is not None
    assert front.error.code == codes.OA_CAM_001
    assert front.warnings  # a warning was surfaced


def test_every_camera_dead_still_lets_the_arm_proceed() -> None:
    """Even with no camera alive, the arm is never blocked (`FR-CAM-084`)."""
    registry = registry_with("wrist", "front", "fallback")
    probes = {
        "wrist": dead_camera("wrist"),
        "front": dead_camera("front"),
        "fallback": dead_camera("fallback"),
    }
    report = tolerant_connect(registry, _three_camera_binding(), _three_descriptors(), probes)

    assert report.opened == ()
    assert len(report.skipped) == 3
    assert report.arm_may_proceed is True
    assert report.blocking_failures == ()


def test_disconnected_serial_is_skipped_not_raised() -> None:
    """A bound serial absent from the bus is a DISCONNECTED skip, not a connect failure."""
    registry = registry_with("wrist")
    # Bind wrist to a serial no descriptor carries.
    report = tolerant_connect(registry, {"wrist": "rs-not-attached"}, _three_descriptors(), {})

    wrist = report.by_slot("wrist")
    assert wrist.status is ConnectStatus.SKIPPED
    assert wrist.reason is SkipReason.DISCONNECTED
    assert wrist.error is not None
    assert report.arm_may_proceed is True


def test_open_that_raises_is_absorbed_as_open_failed() -> None:
    """A probe that raises is a dead camera, caught and skipped — never propagated."""
    registry = registry_with("wrist")
    report = tolerant_connect(
        registry, {"wrist": "rs-0001"}, [camfx.realsense_rgbd()], {"wrist": RaisingProbe()}
    )

    wrist = report.by_slot("wrist")
    assert wrist.status is ConnectStatus.SKIPPED
    assert wrist.reason is SkipReason.OPEN_FAILED
    assert report.arm_may_proceed is True


def test_missing_handle_is_open_failed() -> None:
    """A camera on the bus with no probe (no handle) is skipped OPEN_FAILED."""
    registry = registry_with("wrist")
    report = tolerant_connect(registry, {"wrist": "rs-0001"}, [camfx.realsense_rgbd()], {})

    wrist = report.by_slot("wrist")
    assert wrist.status is ConnectStatus.SKIPPED
    assert wrist.reason is SkipReason.OPEN_FAILED


def test_registered_but_unbound_camera_is_skipped() -> None:
    """A registered camera with no serial bound is a tolerated UNBOUND skip."""
    registry = registry_with("wrist", "front")
    # Only bind wrist; front stays unbound.
    report = tolerant_connect(
        registry, {"wrist": "rs-0001"}, [camfx.realsense_rgbd()], {"wrist": live_camera("wrist")}
    )

    front = report.by_slot("front")
    assert front.status is ConnectStatus.SKIPPED
    assert front.reason is SkipReason.UNBOUND
    assert front.serial is None
    assert report.by_slot("wrist").is_opened
    assert report.arm_may_proceed is True


def test_index_binding_is_rejected_before_connect() -> None:
    """An enumeration-index binding is a config error and raises (`FR-CAM-004`)."""
    registry = registry_with("wrist")
    with pytest.raises(IndexBindingError):
        tolerant_connect(registry, {"wrist": 0}, [camfx.realsense_rgbd()], {})


def test_binding_to_unregistered_slot_is_rejected() -> None:
    """Binding a serial to a slot no camera was registered under is a config error."""
    registry = registry_with("wrist")
    with pytest.raises(BindingError, match="no camera is registered"):
        tolerant_connect(registry, {"ghost": "rs-0001"}, [camfx.realsense_rgbd()], {})
