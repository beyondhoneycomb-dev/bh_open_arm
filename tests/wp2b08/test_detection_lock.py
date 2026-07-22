"""WP-2B-08 acceptance CG-2B-08c: the detection-enable UI is locked at the code level.

FR-SAF-030 forces collision detection DISABLED until the v2 friction model is identified. Path B
is that unidentified state, so the lock must genuinely bite: `enabled` is a constant False, every
enable path raises, and no activating detection method is accepted. These tests are the fault
injection that proves there is no bypass.
"""

from __future__ import annotations

import pytest

from backend.pathb import (
    DETECTION_METHOD_DISABLED,
    DetectionLock,
    DetectionLockError,
    PathBBootstrap,
)


def test_detection_reports_disabled(bootstrap: PathBBootstrap) -> None:
    """Detection is DISABLED and not enabled on a fresh path-B bootstrap."""
    assert bootstrap.detection.enabled is False
    assert bootstrap.detection.method == DETECTION_METHOD_DISABLED


def test_enable_is_blocked() -> None:
    """Calling `enable()` raises rather than flipping detection on."""
    lock = DetectionLock()
    with pytest.raises(DetectionLockError):
        lock.enable()
    assert lock.enabled is False


def test_activating_methods_are_refused() -> None:
    """Every non-DISABLED detection method is refused."""
    lock = DetectionLock()
    for method in ("MOMENTUM_OBSERVER", "TORQUE_RESIDUAL", "CURRENT_LIMIT"):
        with pytest.raises(DetectionLockError):
            lock.set_method(method)
    assert lock.enabled is False


def test_disabled_method_is_accepted() -> None:
    """Re-asserting DISABLED is a no-op, not an error — the lock only refuses activation."""
    lock = DetectionLock()
    lock.set_method(DETECTION_METHOD_DISABLED)
    assert lock.method == DETECTION_METHOD_DISABLED


def test_enabled_has_no_setter() -> None:
    """`enabled` is read-only: there is no attribute a caller can assign to bypass the lock."""
    lock = DetectionLock()
    with pytest.raises(AttributeError):
        lock.enabled = True  # type: ignore[misc]
