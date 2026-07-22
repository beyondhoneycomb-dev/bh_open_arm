"""Fixtures for the WP-2D-09 behavioural tests.

Every fixture here builds the reused primitives — the Cartesian jog (WP-2D-01) and the
jog-path clamp (WP-2A-03) — so the heavy imports live inside the fixture bodies, not at
module top. That keeps ``conftest`` importable in the light lane (where the robot stack
is absent), so the static tests in this directory still collect; a behavioural test that
uses a fixture has already ``importorskip``-ed the stack at its own module top.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from backend.actuation.safety import SafetyLimits
    from backend.moveto import NumericMoveTo

# A fast, low-iteration IK budget: the Move-to tests assert admissibility and commit
# decisions, not convergence accuracy, so a cheap solve keeps the suite quick.
_FAST_IK = {"max_iters": 5, "dt": 0.1, "damping": 0.1, "posture_cost": 0.01, "lm_damping": 0.01}

# Valid, permissive rate and torque axes for the test envelope. The Move-to gate does
# not enforce these — only the position envelope — but `SafetyLimits.validate` requires
# them present, so the tests supply concrete values rather than the module inventing any.
_RATE_TORQUE = {
    "velocity_limit_rad_s": 2.0,
    "accel_limit_rad_s2": 10.0,
    "jerk_limit_rad_s3": 100.0,
    "step_delta_limit_rad": 0.3,
    "peak_torque_nm": 30.0,
    "operational_torque_nm": 25.0,
}


def _fast_ik_params() -> Any:
    """Build the shared fast IK params (robot stack imported lazily)."""
    from openarm_control.kinematics import IKParams

    return IKParams(**_FAST_IK)


@pytest.fixture
def default_limits() -> SafetyLimits:
    """A 16-dim envelope whose operational bound equals the soft-limit mechanical one."""
    from backend.moveto import move_to_limits_from_soft_limits

    return move_to_limits_from_soft_limits(**_RATE_TORQUE)


@pytest.fixture
def gate(default_limits: SafetyLimits) -> NumericMoveTo:
    """A Move-to gate over the default envelope and a fresh fixed-cell jog."""
    from backend.cartesian_jog import build_cartesian_jog
    from backend.jogclamp import JogClampPath
    from backend.moveto import NumericMoveTo

    jog = build_cartesian_jog(ik_params=_fast_ik_params())
    return NumericMoveTo(jog=jog, clamp=JogClampPath(default_limits))


@pytest.fixture
def tight_operational_gate() -> NumericMoveTo:
    """A gate whose right joint4 operational band excludes the home pose (joint4 ≈ 90°).

    Used to prove the limit check on an EE solution is not redundant with the IK-
    existence check: a pose the adapter solves within the mechanical (soft) limits is
    still refused when its joint4 leaves this tighter operational band.
    """
    from backend.cartesian_jog import build_cartesian_jog
    from backend.jogclamp import JogClampPath
    from backend.moveto import (
        NumericMoveTo,
        move_to_limits_from_soft_limits,
        soft_limit_mechanical_deg,
    )
    from backend.moveto.constants import arm_slot_base
    from contracts.units import Deg

    mechanical = soft_limit_mechanical_deg()
    operational = list(mechanical)
    right_joint4_slot = arm_slot_base("right") + 3
    low, _ = mechanical[right_joint4_slot]
    operational[right_joint4_slot] = (low, Deg(45.0))
    limits = move_to_limits_from_soft_limits(operational_deg=tuple(operational), **_RATE_TORQUE)
    jog = build_cartesian_jog(ik_params=_fast_ik_params())
    return NumericMoveTo(jog=jog, clamp=JogClampPath(limits))
