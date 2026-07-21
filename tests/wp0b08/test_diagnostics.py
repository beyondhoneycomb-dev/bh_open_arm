"""Acceptance ⑦ (message half) — the frame-timeout diagnostic names both causes.

FR-CAM-013 requires "Frame did not arrive in time" to be reported as *both* a bandwidth
and a power fault, because the two are indistinguishable from the error alone. The
message builder runs here; provoking the real error under load needs a real starved
camera and is the deferred half, re-run by the reverify hook against a captured string.
"""

from __future__ import annotations

from backend.camera.diagnostics import (
    FRAME_TIMEOUT_ERROR,
    diagnose_frame_timeout,
    is_frame_timeout,
)


def test_diagnostic_names_both_bandwidth_and_power() -> None:
    """The message must mention both causes, not pick one (FR-CAM-013)."""
    message = diagnose_frame_timeout("rs-0001 (D435)").lower()
    assert "bandwidth" in message
    assert "power" in message
    assert "rs-0001" in message


def test_classifier_recognises_the_error() -> None:
    """The frame-timeout string is recognised case-insensitively."""
    assert is_frame_timeout(f"RuntimeError: {FRAME_TIMEOUT_ERROR}")
    assert is_frame_timeout("frame did not arrive in time")
    assert not is_frame_timeout("some other camera error")
