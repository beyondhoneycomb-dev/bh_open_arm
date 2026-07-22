"""RUNS ③ (CG-3B-09b) — the smoother resets on INVALID->valid and on re-engage.

`FR-TEL-040` / `05` §2.7 ⓔ: the One Euro smoother's `reset()` MUST be called when
tracking validity returns from INVALID and when the clutch re-engages; the WebXR path
shipped without it and jumped on re-entry. A missed reset is the `FAIL_BLOCKING` defect,
so the last test reproduces the re-entry transient a missing reset leaves behind.
"""

from __future__ import annotations

import numpy as np

from backend.teleop.clutch import OneEuroPoseSmoother, TeleopPoseConditioner, ValidityTracker
from contracts.teleop import TeleopValidity
from tests.wp3b09._support import IDENTITY_QUAT, make_frame

_ENGAGE_GRIP = 0.95
_RELEASE_GRIP = 0.0
_FRAME_NS = 16_000_000  # ~60 Hz
_EE = np.array([0.0, 0.0, 0.0])
_EE_QUAT = np.array(IDENTITY_QUAT)


def test_validity_tracker_flags_only_the_recovery_edge() -> None:
    """The INVALID->valid edge is reported once, on the first publishable sample after INVALID."""
    tracker = ValidityTracker()
    assert tracker.update(TeleopValidity.OK) is False  # first sample is never an edge
    assert tracker.update(TeleopValidity.OK) is False
    assert tracker.update(TeleopValidity.INVALID) is False  # entering INVALID is not the edge
    assert tracker.update(TeleopValidity.OK) is True  # recovery -> reset
    assert tracker.update(TeleopValidity.OK) is False


def test_stale_counts_as_the_recovery_level() -> None:
    """STALE is publishable, so INVALID->STALE is also a recovery edge."""
    tracker = ValidityTracker()
    tracker.update(TeleopValidity.INVALID)
    assert tracker.update(TeleopValidity.STALE) is True


def _process(conditioner: TeleopPoseConditioner, grip: float, validity: TeleopValidity, tick: int):
    """Drive the conditioner one tick with a fixed pose, returning the result."""
    frame = make_frame(grip, validity, (0.0, 0.0, 0.0), IDENTITY_QUAT, tick * _FRAME_NS)
    return conditioner.process(frame, "right", _EE, _EE_QUAT)


def _process_at(
    conditioner: TeleopPoseConditioner,
    grip: float,
    validity: TeleopValidity,
    tick: int,
    position: tuple[float, float, float],
):
    """Drive the conditioner one tick with a chosen controller position."""
    frame = make_frame(grip, validity, position, IDENTITY_QUAT, tick * _FRAME_NS)
    return conditioner.process(frame, "right", _EE, _EE_QUAT)


def test_recovery_reset_actually_flushes_the_smoother_effect() -> None:
    """The INVALID->valid reset is verified by its EFFECT on the output, not just the flag.

    Asserting `smoother_reset is True` (as the tests above do) only checks the reported
    flag, which `ValidityTracker` computes independently of whether `smoother.reset()`
    actually fired — so deleting the reset call would still pass those. This test drives
    the conditioner across a real INVALID gap: it converges the smoother at a FAR target,
    then recovers at the reference pose (raw target back to the EE origin). Only a smoother
    that truly reset emits the fresh origin on the first resumed tick; a smoother carrying
    stale state lags toward the far plateau. So this bites if the `reset()` call is removed.
    """
    conditioner = TeleopPoseConditioner()
    # Engage at the reference pose (reference captured here => raw target starts at the EE).
    first = _process_at(conditioner, _ENGAGE_GRIP, TeleopValidity.OK, 0, (0.0, 0.0, 0.0))
    assert first.smoother_reset is True

    # Move the controller far and hold, so the smoother converges on a far, non-origin target.
    far = (1.0, 0.0, 0.0)
    for tick in range(1, 40):
        _process_at(conditioner, _ENGAGE_GRIP, TeleopValidity.OK, tick, far)
    plateau = _process_at(conditioner, _ENGAGE_GRIP, TeleopValidity.OK, 40, far)
    assert plateau.target is not None
    assert np.linalg.norm(plateau.target.position) > 0.3  # genuinely far from the origin

    # INVALID gap (withheld), then recover AT the reference pose: raw target back to the EE origin.
    withheld = _process_at(conditioner, _ENGAGE_GRIP, TeleopValidity.INVALID, 41, (0.0, 0.0, 0.0))
    assert withheld.published is False
    recovered = _process_at(conditioner, _ENGAGE_GRIP, TeleopValidity.OK, 42, (0.0, 0.0, 0.0))

    assert recovered.smoother_reset is True
    assert recovered.target is not None
    # Reset flushed the far plateau -> the first resumed sample is the fresh origin, no transient.
    # Without the reset the smoother would still sit near the far plateau (> 0.3 away from origin).
    assert np.allclose(recovered.target.position, _EE, atol=1e-6)


def test_conditioner_resets_on_validity_recovery() -> None:
    """A reset fires on the recovery tick, and only then, while gripping continuously."""
    conditioner = TeleopPoseConditioner()
    first = _process(conditioner, _ENGAGE_GRIP, TeleopValidity.OK, 0)
    assert first.smoother_reset is True  # first engage also resets (fresh start)

    steady = _process(conditioner, _ENGAGE_GRIP, TeleopValidity.OK, 1)
    assert steady.smoother_reset is False

    withheld = _process(conditioner, _ENGAGE_GRIP, TeleopValidity.INVALID, 2)
    assert withheld.published is False
    assert withheld.smoother_reset is False  # entering INVALID is not the reset moment

    recovered = _process(conditioner, _ENGAGE_GRIP, TeleopValidity.OK, 3)
    assert recovered.published is True
    assert recovered.smoother_reset is True  # FR-TEL-040: reset on INVALID->valid

    after = _process(conditioner, _ENGAGE_GRIP, TeleopValidity.OK, 4)
    assert after.smoother_reset is False


def test_conditioner_resets_on_reengage() -> None:
    """A reset fires on the clutch rising edge after a release, and not while held."""
    conditioner = TeleopPoseConditioner()
    _process(conditioner, _ENGAGE_GRIP, TeleopValidity.OK, 0)  # first engage
    held = _process(conditioner, _ENGAGE_GRIP, TeleopValidity.OK, 1)
    assert held.smoother_reset is False

    released = _process(conditioner, _RELEASE_GRIP, TeleopValidity.OK, 2)
    assert released.engaged is False
    assert released.smoother_reset is False

    reengaged = _process(conditioner, _ENGAGE_GRIP, TeleopValidity.OK, 3)
    assert reengaged.reference_captured is True
    assert reengaged.smoother_reset is True  # FR-TEL-040: reset on re-engage


def test_missing_reset_leaves_a_reentry_transient() -> None:
    """A missed reset filters the first resumed sample against stale state; reset passes it through.

    This is the `FAIL_BLOCKING` defect made observable: converge on pose A, then resume
    at a far pose B one frame later (as after an INVALID gap). The reset smoother emits B
    exactly; the un-reset smoother emits a value short of B — a re-entry discontinuity.
    """
    pose_a = np.array([0.0, 0.0, 0.0])
    pose_b = np.array([1.0, 0.0, 0.0])
    dt_ns = _FRAME_NS

    def converge(smoother: OneEuroPoseSmoother) -> None:
        for tick in range(30):
            smoother.filter(pose_a, _EE_QUAT, tick * dt_ns / 1e9)

    reset_smoother = OneEuroPoseSmoother()
    converge(reset_smoother)
    reset_smoother.reset()
    reset_out = reset_smoother.filter(pose_b, _EE_QUAT, 30 * dt_ns / 1e9)

    defect_smoother = OneEuroPoseSmoother()
    converge(defect_smoother)
    defect_out = defect_smoother.filter(pose_b, _EE_QUAT, 30 * dt_ns / 1e9)

    assert np.allclose(reset_out.position, pose_b)  # reset -> exact pass-through, no artifact
    assert not np.allclose(defect_out.position, pose_b)  # no reset -> resumed pose is distorted
    assert np.linalg.norm(defect_out.position - pose_b) > 0.1
