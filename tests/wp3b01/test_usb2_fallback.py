"""Acceptance ③ (CG-3B-01c) — a USB2 fallback is warned, and over-budget profiles blocked.

`FR-CAM-003`: a camera that negotiated a USB2 link opens but is flagged, and any
profile whose `06` §2.9 bandwidth overruns the USB2 budget is refused. The bandwidth
formula is reused from `backend.camera.bandwidth` — there is one source of truth for it.
"""

from __future__ import annotations

from backend.camera import fixtures as camfx
from backend.sensing.connect import USB2_NOMINAL_MBPS, tolerant_connect
from tests.wp3b01._support import live_camera, registry_with, usb2_descriptor


def test_usb2_fallback_opens_but_is_warned() -> None:
    """A USB2 camera with a profile inside budget opens, flagged, with nothing blocked."""
    registry = registry_with("fallback")
    descriptor = usb2_descriptor("uvc-fallback-480", heavy=False)
    report = tolerant_connect(
        registry,
        {"fallback": "uvc-fallback-480"},
        [descriptor],
        {"fallback": live_camera("fallback")},
    )

    outcome = report.by_slot("fallback")
    assert outcome.is_opened
    assert outcome.is_usb2_fallback
    assert outcome.warnings  # the USB2 fallback is surfaced
    assert outcome.blocked_profiles == ()
    assert [o.slot for o in report.usb2_fallbacks] == ["fallback"]


def test_usb2_over_budget_profile_is_blocked() -> None:
    """A USB2 camera whose profile exceeds the budget has that profile refused."""
    registry = registry_with("fallback")
    descriptor = usb2_descriptor("uvc-heavy-720", heavy=True)
    report = tolerant_connect(
        registry,
        {"fallback": "uvc-heavy-720"},
        [descriptor],
        {"fallback": live_camera("fallback")},
    )

    outcome = report.by_slot("fallback")
    assert outcome.is_opened  # still opens — the block is on the profile, not the camera
    assert len(outcome.blocked_profiles) == 1
    blocked = outcome.blocked_profiles[0]
    assert blocked.required_mbps > blocked.budget_mbps
    assert blocked.budget_mbps == float(USB2_NOMINAL_MBPS)
    assert len(report.blocked_profiles) == 1


def test_custom_usb2_budget_changes_the_block() -> None:
    """The USB2 budget is a parameter: a tighter budget blocks a profile the default passes."""
    registry = registry_with("fallback")
    descriptor = usb2_descriptor("uvc-fallback-480", heavy=False)  # 147.5 Mbps, fits 480

    passes = tolerant_connect(
        registry,
        {"fallback": "uvc-fallback-480"},
        [descriptor],
        {"fallback": live_camera("fallback")},
    )
    assert passes.by_slot("fallback").blocked_profiles == ()

    blocked = tolerant_connect(
        registry,
        {"fallback": "uvc-fallback-480"},
        [descriptor],
        {"fallback": live_camera("fallback")},
        usb2_budget_mbps=100.0,  # below 147.5 Mbps, so now refused
    )
    assert len(blocked.by_slot("fallback").blocked_profiles) == 1


def test_usb3_camera_carries_no_usb2_warning() -> None:
    """A camera on a USB3 link is not a fallback and raises no USB2 finding."""
    registry = registry_with("wrist")
    report = tolerant_connect(
        registry, {"wrist": "rs-0001"}, [camfx.realsense_rgbd()], {"wrist": live_camera("wrist")}
    )
    outcome = report.by_slot("wrist")
    assert outcome.is_opened
    assert not outcome.is_usb2_fallback
    assert outcome.warnings == ()
    assert report.usb2_fallbacks == ()
