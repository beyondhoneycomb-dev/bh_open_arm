"""IK output → CTR-ACT AcceptedPositionAction, crossing rad→deg once (01 FR-SYS-016).

The adapter's clean output is a 16-dim ``AcceptedPositionAction`` in degrees, produced
by clamping the radian IK solution to the LeRobot soft limits and crossing to degrees
through the single CTR-UNIT ``rad_to_deg`` boundary. A held cycle still yields a valid
in-limits action (the last valid pose), never an out-of-limits one.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

pytest.importorskip("mujoco")
pytest.importorskip("mink")
pytest.importorskip("lerobot")

from openarm_control.kinematics import IKParams

from contracts.action.channels import BIMANUAL_ACTION_DIM, AcceptedPositionAction
from contracts.units.tags import Deg
from sim.ik.adapter import _to_accepted_action, build_ik_adapter
from sim.ik.limits import all_soft_limits

_IK_PARAMS = {"dt": 0.1, "damping": 0.1, "posture_cost": 0.01, "lm_damping": 0.01}


def test_clean_solve_yields_degrees_action() -> None:
    adapter = build_ik_adapter(ik_params=IKParams(max_iters=10, **_IK_PARAMS))
    adapter.set_target("right", adapter._kin.setup.read_ee_pose("right"))
    adapter.set_target("left", adapter._kin.setup.read_ee_pose("left"))
    outcome = adapter.solve()

    assert outcome.held is False
    assert outcome.faults == ()
    assert isinstance(outcome.accepted, AcceptedPositionAction)
    assert len(outcome.accepted.values) == BIMANUAL_ACTION_DIM
    assert all(isinstance(value, Deg) for value in outcome.accepted.values)


def test_rad_to_deg_boundary_is_exact() -> None:
    solution = np.full(BIMANUAL_ACTION_DIM, 0.5, dtype=np.float32)
    action = _to_accepted_action(solution)
    for value in action.values:
        assert value.value == pytest.approx(math.degrees(0.5), abs=1e-5)


def test_held_action_is_within_limits() -> None:
    # Force a HOLD via the enabled fallback; the accepted action is the last valid
    # (home) pose, which is inside every soft limit.
    adapter = build_ik_adapter(
        ik_params=IKParams(max_iters=1, **_IK_PARAMS),
        allow_unconstrained_fallback=True,
    )
    upper = np.array([limit.upper_rad.value for limit in all_soft_limits()], dtype=float)
    adapter.sync((upper + 1.0).astype(np.float32))
    adapter.set_target("right", adapter._kin.setup.read_ee_pose("right"))
    adapter.set_target("left", adapter._kin.setup.read_ee_pose("left"))
    outcome = adapter.solve()

    assert outcome.held is True
    assert isinstance(outcome.accepted, AcceptedPositionAction)
    limits = all_soft_limits()
    for slot, limit in enumerate(limits):
        deg = outcome.accepted.values[slot].value
        assert math.radians(deg) <= limit.upper_rad.value + 1e-6
        assert math.radians(deg) >= limit.lower_rad.value - 1e-6


def test_action_dimension_is_enforced() -> None:
    with pytest.raises(ValueError, match="16-dim"):
        _to_accepted_action(np.zeros(10, dtype=np.float32))
