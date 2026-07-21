"""Acceptance ⑥ — the four FR-OPS-043 conditions each carry a distinct code.

Each of the four failure conditions is provoked in isolation and asserted to report
its own ``OA-IK-00x`` — never a single merged "IK failure". The codes themselves are
checked to be four distinct values.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("mujoco")
pytest.importorskip("mink")
pytest.importorskip("lerobot")

from openarm_control.kinematics import IKParams

from sim.ik.adapter import build_ik_adapter
from sim.ik.faults import IkFault, IkFaultCode
from sim.ik.limits import all_soft_limits

_IK_PARAMS = {"dt": 0.1, "damping": 0.1, "posture_cost": 0.01, "lm_damping": 0.01}


def _out_of_limit_config() -> np.ndarray:
    upper = np.array([limit.upper_rad.value for limit in all_soft_limits()], dtype=float)
    return (upper + 1.0).astype(np.float32)


def _codes(faults: tuple[IkFault, ...]) -> set[IkFaultCode]:
    return {fault.code for fault in faults}


def test_the_four_codes_are_distinct() -> None:
    values = {code.value for code in IkFaultCode}
    assert values == {"OA-IK-001", "OA-IK-002", "OA-IK-003", "OA-IK-004"}
    assert len(IkFaultCode) == 4


def test_solve_none_reports_its_own_code() -> None:
    adapter = build_ik_adapter(ik_params=IKParams(max_iters=3, **_IK_PARAMS))
    adapter.sync(_out_of_limit_config())
    adapter.set_target("right", adapter._kin.setup.read_ee_pose("right"))
    adapter.set_target("left", adapter._kin.setup.read_ee_pose("left"))
    outcome = adapter.solve()
    assert IkFaultCode.SOLVE_NONE in _codes(outcome.faults)
    assert IkFaultCode.UNCONSTRAINED_FALLBACK not in _codes(outcome.faults)


def test_residual_reports_its_own_code() -> None:
    # One iteration toward a shifted target leaves an EE residual; an impossibly tight
    # threshold makes the residual the sole fault.
    adapter = build_ik_adapter(ik_params=IKParams(max_iters=1, **_IK_PARAMS), residual_max_m=1e-12)
    target_right = adapter._kin.setup.read_ee_pose("right").copy()
    target_right[0] += 0.15
    adapter.set_target("right", target_right)
    adapter.set_target("left", adapter._kin.setup.read_ee_pose("left"))
    outcome = adapter.solve()
    assert IkFaultCode.EE_RESIDUAL_EXCEEDED in _codes(outcome.faults)


def test_fallback_and_clamp_are_separately_coded() -> None:
    # The enabled fallback produces an out-of-limit solution: the firing is OA-IK-003
    # and the resulting clamp is OA-IK-004 — two distinct codes, not one verdict.
    adapter = build_ik_adapter(
        ik_params=IKParams(max_iters=1, **_IK_PARAMS),
        allow_unconstrained_fallback=True,
    )
    adapter.sync(_out_of_limit_config())
    adapter.set_target("right", adapter._kin.setup.read_ee_pose("right"))
    adapter.set_target("left", adapter._kin.setup.read_ee_pose("left"))
    outcome = adapter.solve()
    codes = _codes(outcome.faults)
    assert IkFaultCode.UNCONSTRAINED_FALLBACK in codes
    assert IkFaultCode.JOINT_LIMIT_CLAMP in codes


def test_reporter_keeps_codes_apart() -> None:
    from sim.ik.faults import FaultReporter

    reporter = FaultReporter()
    reporter.report(IkFault(code=IkFaultCode.UNCONSTRAINED_FALLBACK, detail="a"))
    reporter.report(IkFault(code=IkFaultCode.UNCONSTRAINED_FALLBACK, detail="b"))
    reporter.report(IkFault(code=IkFaultCode.JOINT_LIMIT_CLAMP, detail="c", joint="j"))
    counts = reporter.counts_by_code()
    assert counts[IkFaultCode.UNCONSTRAINED_FALLBACK] == 2
    assert counts[IkFaultCode.JOINT_LIMIT_CLAMP] == 1
    assert set(reporter.codes()) == {
        IkFaultCode.UNCONSTRAINED_FALLBACK,
        IkFaultCode.JOINT_LIMIT_CLAMP,
    }
