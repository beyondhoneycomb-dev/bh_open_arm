"""Acceptance ② and ③ — mechanical-limit stop and controlled unconstrained fallback.

② An IK solution that leaves the canonical mechanical limits is discarded and the jog
   stops. The redundant first-line-of-defense guard is exercised directly, and the
   adapter-clamp path is driven end to end through the jog.
③ The unconstrained fallback is off by default; when explicitly enabled and fired, the
   jog reports the fault (``OA-IK-003``) rather than swallowing it.

The out-of-limit driver seed is the deterministic trigger: seeded outside the tightened
soft limits, the constrained QP is infeasible every iteration (WP-0C-02's mechanism),
which the jog surfaces as a stop.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("mujoco")
pytest.importorskip("mink")
pytest.importorskip("lerobot")

from openarm_control.kinematics import IKParams

from backend.cartesian_jog import JogAxis, JogCommand, JogKind, build_cartesian_jog
from backend.cartesian_jog.jog import JogStopReason, _mechanical_limit_violations
from sim.ik.faults import IkFaultCode
from sim.ik.limits import all_soft_limits

_FAST = {"dt": 0.1, "damping": 0.1, "posture_cost": 0.01, "lm_damping": 0.01}


def _out_of_limit_config() -> np.ndarray:
    upper = np.array([limit.upper_rad.value for limit in all_soft_limits()], dtype=float)
    return upper + 1.0


def _z_jog(side: str = "right") -> JogCommand:
    return JogCommand(side=side, kind=JogKind.TRANSLATION, axis=JogAxis.Z, sign=1)


def test_independent_guard_flags_a_solution_outside_the_canonical_limits() -> None:
    # The redundant guard is the 1st line of defense: an out-of-limit solution is caught
    # even though the adapter clamp already runs — belt and suspenders (02b §4.3).
    assert _mechanical_limit_violations(_out_of_limit_config()) != []
    # A home-valid solution has no violation.
    from backend.cartesian_jog.frames import KinematicFrames

    assert _mechanical_limit_violations(KinematicFrames().home_solution()) == []
    # None (no solution) yields no violation list — the None path is a different stop.
    assert _mechanical_limit_violations(None) == []


def test_limit_violating_solution_discards_step_and_stops_the_jog() -> None:
    jog = build_cartesian_jog(
        ik_params=IKParams(max_iters=1, **_FAST), allow_unconstrained_fallback=True
    )
    jog.seed(_out_of_limit_config())
    before = jog.committed_solution()

    result = jog.step(_z_jog())

    # The out-of-limit fallback solution is clamped (OA-IK-004): step discarded, jog stops.
    assert result.stopped is True
    assert result.committed is False
    assert result.reason is JogStopReason.LIMIT
    assert np.allclose(before, jog.committed_solution())
    assert jog.steps_committed == 0


def test_fallback_is_disabled_by_default() -> None:
    jog = build_cartesian_jog(ik_params=IKParams(max_iters=3, **_FAST))
    assert jog.allow_unconstrained_fallback is False


def test_default_fallback_holds_on_no_solution_without_firing() -> None:
    jog = build_cartesian_jog(ik_params=IKParams(max_iters=3, **_FAST))
    jog.seed(_out_of_limit_config())

    result = jog.step(_z_jog())

    assert result.fallback_fired is False
    assert result.reason is JogStopReason.NO_SOLUTION
    assert not any(f.code is IkFaultCode.UNCONSTRAINED_FALLBACK for f in result.faults)


def test_enabled_fallback_fires_and_is_reported() -> None:
    jog = build_cartesian_jog(
        ik_params=IKParams(max_iters=1, **_FAST), allow_unconstrained_fallback=True
    )
    jog.seed(_out_of_limit_config())

    result = jog.step(_z_jog())

    assert result.fallback_fired is True
    assert any(f.code is IkFaultCode.UNCONSTRAINED_FALLBACK for f in result.faults)
    # A fired fallback still stops the jog — it is never a silent success.
    assert result.stopped is True
