"""WP-2C-02 acceptance ①: activation is code-level LOCKED while PG-FRIC-001 has not passed.

FR-SAF-030 makes detection a function of PG-FRIC-001 PASS. Until it passes, the activation UI/API
must genuinely refuse: the resolved mode is DISABLED, `activation_permitted` is False, the
assert-guards raise, and the verdict is frozen so no attribute can be flipped to bypass the lock.
On this host PG-FRIC-001 is hardware-deferred, so these are the tests that prove the LOCK; the
synthetic-PASS cases exercise the permit logic without claiming the real gate is open.
"""

from __future__ import annotations

import dataclasses

import pytest

from backend.detection_gate import (
    DetectionActivationMode,
    DetectionActivationRefusedError,
    assert_activation_allowed,
    measure_and_resolve,
    resolve_activation,
)
from backend.safety_bringup.band import FramePattern, resolve_detection_band

NON_PASS_STATUSES = ("FAIL_BLOCKING", "RETRY_WITH_VARIANT", "DEGRADED_ACCEPTED", "SUPERSEDED", "")


def test_deferred_status_locks_activation(deferred_status: str, fmax_deferred) -> None:
    """With PG-FRIC-001 not passed, the gate resolves DISABLED and refuses activation."""
    activation = measure_and_resolve(deferred_status, FramePattern.A, fmax_deferred)
    assert activation.mode is DetectionActivationMode.DISABLED
    assert activation.locked is True
    assert activation.activation_permitted is False
    with pytest.raises(DetectionActivationRefusedError):
        activation.assert_can_activate()


@pytest.mark.parametrize("status", NON_PASS_STATUSES)
def test_every_non_pass_status_locks(status: str, fmax_deferred) -> None:
    """Any PG-FRIC-001 state other than PASS locks activation — PASS is the only key."""
    activation = measure_and_resolve(status, FramePattern.B, fmax_deferred)
    assert activation.mode is DetectionActivationMode.DISABLED
    assert activation.locked is True


def test_api_guard_refuses_without_pass(deferred_status: str) -> None:
    """The API-level `assert_activation_allowed` raises at the door for a non-PASS verdict."""
    with pytest.raises(DetectionActivationRefusedError):
        assert_activation_allowed(deferred_status)


def test_api_guard_permits_pass(synthetic_pass: str) -> None:
    """`assert_activation_allowed` returns for a PASS verdict (logic check, synthetic status)."""
    assert_activation_allowed(synthetic_pass)


def test_disabled_verdict_is_frozen_no_bypass(deferred_status: str, fmax_deferred) -> None:
    """The verdict is frozen: no attribute can be assigned to flip a DISABLED lock to permitted."""
    activation = measure_and_resolve(deferred_status, FramePattern.A, fmax_deferred)
    with pytest.raises(dataclasses.FrozenInstanceError):
        activation.mode = DetectionActivationMode.ACTIVE  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        activation.speed_cap_scale = 0.5  # type: ignore[misc]


def test_pass_with_full_band_permits(synthetic_pass: str, fmax_deferred) -> None:
    """A synthetic PASS with a 1 kHz-capable band resolves ACTIVE and permits activation."""
    activation = measure_and_resolve(synthetic_pass, FramePattern.A, fmax_deferred)
    assert activation.mode is DetectionActivationMode.ACTIVE
    assert activation.activation_permitted is True
    assert activation.locked is False
    activation.assert_can_activate()


def test_band_alone_never_unlocks(deferred_status: str, fmax_deferred) -> None:
    """A fully-active band cannot unlock a not-PASS friction verdict — PASS gates it."""
    full_band = resolve_detection_band(FramePattern.A, fmax_deferred)
    assert full_band.degraded is False
    activation = resolve_activation(deferred_status, full_band)
    assert activation.mode is DetectionActivationMode.DISABLED
