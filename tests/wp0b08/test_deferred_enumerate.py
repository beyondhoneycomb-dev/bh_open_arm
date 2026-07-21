"""Acceptance ①②③ (deferred) — real enumeration honestly skips without cameras.

There are no cameras and no RealSense/udev backends on this host, so live enumeration,
USB2-fallback detection from a real link, and controller membership from a real bus
cannot be verified. This module proves the deferral is honest rather than a faked
green: `enumerate_cameras` refuses to fabricate a descriptor (it raises), and the
re-verification hook that will run these checks on real bytes exists and is importable.
"""

from __future__ import annotations

import pytest

from backend.camera import reverify
from backend.camera.enumerate_hw import (
    HardwareUnavailableError,
    backend_availability,
    enumerate_cameras,
    real_enumeration_supported,
)

_needs_no_backends = pytest.mark.skipif(
    all(backend_availability()[m] for m in ("pyrealsense2", "pyudev")),
    reason="RealSense/udev backends are installed; real enumeration path is exercisable "
    "and this no-backend deferral no longer applies",
)


@_needs_no_backends
def test_real_enumeration_is_unsupported_here_with_a_reason() -> None:
    """Without the enumeration backends, the harness reports unsupported and why."""
    supported, reason = real_enumeration_supported()
    assert supported is False
    assert "backend" in reason


@_needs_no_backends
def test_enumerate_refuses_to_fabricate() -> None:
    """Live enumeration raises rather than returning a fake camera (no faked green)."""
    with pytest.raises(HardwareUnavailableError):
        enumerate_cameras()


def test_reverification_hook_exists_for_the_deferred_checks() -> None:
    """The deferred acceptances ship a real-fixture hook, per plan 02a §4.1."""
    assert hasattr(reverify, "reverify_from_fixture")
    assert reverify.FIXTURE_ENV_VAR == "OPENARM_CAMERA_REAL_FIXTURE"
