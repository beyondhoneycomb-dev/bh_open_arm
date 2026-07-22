"""Acceptance ② (CG-3B-01b) — a slot keeps its camera across a reboot/re-plug.

`FR-CAM-004`: binding is by stable serial (or udev symlink), never by enumeration
index, so a reboot that reshuffles enumeration order leaves each slot bound to the
same camera. The connect resolves by serial, so connecting twice against the same
serials — in any order — yields the same slot→serial map. Index-based binding is
rejected, reusing the WP-0B-08 validator.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from backend.camera import fixtures as camfx
from backend.camera.binding import IndexBindingError
from backend.sensing.connect import tolerant_connect
from tests.wp3b01._support import live_camera, registry_with


def _binding() -> dict[str, object]:
    return {"wrist": "rs-0001", "front": "uvc-logitech-720"}


def _probes() -> dict:
    return {"wrist": live_camera("wrist"), "front": live_camera("front")}


def test_reenumeration_reorder_keeps_the_same_slot_binding() -> None:
    """Enumeration order flips on reboot; each slot still resolves to the same serial."""
    registry = registry_with("wrist", "front")
    before = [camfx.realsense_rgbd(), camfx.webcam_720p()]
    after = list(reversed(before))  # a reboot hands enumeration back in a different order

    first = tolerant_connect(registry, _binding(), before, _probes())
    second = tolerant_connect(registry, _binding(), after, _probes())

    assert first.resolved_serials == {"wrist": "rs-0001", "front": "uvc-logitech-720"}
    assert second.resolved_serials == first.resolved_serials


def test_reconnect_after_drop_restores_the_same_slot() -> None:
    """A camera that vanished then re-enumerated binds back to its original slot."""
    registry = registry_with("wrist", "front")

    # Reboot moment: only the webcam is on the bus; the RealSense is briefly gone.
    during = tolerant_connect(registry, _binding(), [camfx.webcam_720p()], _probes())
    assert during.by_slot("wrist").is_skipped  # RealSense absent → skipped, arm proceeds
    assert during.arm_may_proceed is True

    # Recovered: the same serial reappears and rebinds to the same slot.
    after = tolerant_connect(
        registry, _binding(), [camfx.webcam_720p(), camfx.realsense_rgbd()], _probes()
    )
    assert after.resolved_serials["wrist"] == "rs-0001"
    assert after.by_slot("wrist").is_opened


def test_udev_symlink_binding_is_accepted() -> None:
    """A `/dev/v4l/by-id/...` symlink is stable identity, so it binds (not an index)."""
    registry = registry_with("wrist")
    symlink = "/dev/v4l/by-id/usb-Generic_UVC_Camera-video-index0"
    # Rebuild a descriptor under the symlink serial so the binding resolves.
    descriptor = replace(camfx.usb2_fallback_webcam(), serial=symlink)
    report = tolerant_connect(
        registry, {"wrist": symlink}, [descriptor], {"wrist": live_camera("wrist")}
    )
    assert report.resolved_serials == {"wrist": symlink}


@pytest.mark.parametrize("value", [0, 3, "0", "/dev/video0"], ids=["int0", "int", "str0", "node"])
def test_index_binding_shapes_rejected(value: object) -> None:
    """Every enumeration-index shape is refused before it can pin a moving slot."""
    registry = registry_with("wrist")
    with pytest.raises(IndexBindingError):
        tolerant_connect(registry, {"wrist": value}, [camfx.realsense_rgbd()], {})
