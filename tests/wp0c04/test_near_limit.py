"""Acceptance ⑤ — near-limit samples keep the IK output inside the soft limits.

Configurations pinned at the soft-limit boundary command poses at the edge of the
reachable set. Combined with the WP-0C-02 jnt_range override and output clamp, every
solved sample's accepted (post-clamp) action must lie inside the LeRobot limits — no
solution escapes them.
"""

from __future__ import annotations

import pytest

pytest.importorskip("mujoco")
pytest.importorskip("mink")
pytest.importorskip("lerobot")

from openarm_control.kinematics import IKParams

from sim.fkik import roundtrip

_FAST = IKParams(max_iters=5, dt=0.1, damping=0.1, posture_cost=0.01, lm_damping=0.01)


def test_near_limit_solutions_stay_in_limits() -> None:
    report = roundtrip.run_distribution(samples=16, seed=0, ik_params=_FAST, near_limit=True)
    solved = [sample for sample in report.results if sample.solution_produced]
    # The check must not be vacuous: at least one near-limit pose was solved.
    assert solved
    for sample in solved:
        # The override + clamp keep every produced solution inside the soft limits.
        assert sample.raw_solution_in_limits is True
