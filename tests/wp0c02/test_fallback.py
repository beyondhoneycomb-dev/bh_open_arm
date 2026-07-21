"""Acceptance ④ and ⑤ — the unconstrained fallback is off by default, loud when on.

A configuration pushed outside the tightened soft limits makes the constrained QP
infeasible on every iteration, which is the deterministic trigger for the
``limits=[]`` retry (kinematics.py:220-231).

④ With the fallback at its default (disabled), the trigger fires it zero times and
   the solve holds on ``OA-IK-001``.
⑤ With the fallback explicitly enabled, each firing is exactly one ``OA-IK-003``
   fault — one per iteration, never a silent one.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("mujoco")
pytest.importorskip("mink")
pytest.importorskip("lerobot")

from openarm_control.kinematics import IKParams

from sim.ik.adapter import IkAdapter, build_ik_adapter
from sim.ik.faults import IkFaultCode
from sim.ik.limits import all_soft_limits

_IK_PARAMS = {"dt": 0.1, "damping": 0.1, "posture_cost": 0.01, "lm_damping": 0.01}


def _out_of_limit_config() -> np.ndarray:
    upper = np.array([limit.upper_rad.value for limit in all_soft_limits()], dtype=float)
    return (upper + 1.0).astype(np.float32)


def _drive_fallback_trigger(adapter: IkAdapter) -> None:
    adapter.sync(_out_of_limit_config())
    adapter.set_target("right", adapter._kin.setup.read_ee_pose("right"))
    adapter.set_target("left", adapter._kin.setup.read_ee_pose("left"))


def _fallback_firings(faults: tuple) -> int:
    return sum(1 for fault in faults if fault.code is IkFaultCode.UNCONSTRAINED_FALLBACK)


def test_fallback_disabled_by_default_fires_zero() -> None:
    adapter = build_ik_adapter(ik_params=IKParams(max_iters=3, **_IK_PARAMS))
    assert adapter.allow_unconstrained_fallback is False
    _drive_fallback_trigger(adapter)
    outcome = adapter.solve()

    assert _fallback_firings(outcome.faults) == 0
    assert outcome.solution_rad is None
    assert outcome.held is True
    assert IkFaultCode.SOLVE_NONE in {fault.code for fault in outcome.faults}


@pytest.mark.parametrize("max_iters", [1, 2, 5])
def test_fallback_enabled_reports_one_fault_per_firing(max_iters: int) -> None:
    adapter = build_ik_adapter(
        ik_params=IKParams(max_iters=max_iters, **_IK_PARAMS),
        allow_unconstrained_fallback=True,
    )
    _drive_fallback_trigger(adapter)
    outcome = adapter.solve()

    # Every iteration fails constrained and takes the fallback: one firing, one fault.
    assert _fallback_firings(outcome.faults) == max_iters
    assert outcome.held is True


def test_no_silent_fallback() -> None:
    # Whenever the fallback path runs, a fault exists for it; there is no firing that
    # leaves the reporter empty of OA-IK-003.
    adapter = build_ik_adapter(
        ik_params=IKParams(max_iters=1, **_IK_PARAMS),
        allow_unconstrained_fallback=True,
    )
    _drive_fallback_trigger(adapter)
    outcome = adapter.solve()
    assert _fallback_firings(outcome.faults) >= 1
