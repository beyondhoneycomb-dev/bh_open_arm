"""Acceptance ②: waypoint density is auto-computed and an insufficient one refuses the check."""

from __future__ import annotations

import pytest

from backend.collision_preflight.density import (
    DensityInsufficientError,
    assess_density,
    max_joint_step_rad,
    require_sufficient_density,
)
from backend.collision_preflight.model import GeometryExtents, PreflightModel
from backend.collision_preflight.preflight import run_preflight

_ARM = 7


def _neutral(model: PreflightModel) -> tuple[float, ...]:
    return tuple([0.0] * model.nq)


def test_density_formula_is_the_plan_inequality() -> None:
    # swept bound = max joint step x max link radius; sufficient iff below min thickness.
    extents = GeometryExtents(max_link_radius_m=0.11, min_link_thickness_m=0.0093)
    dense = assess_density(([0.0] * 4, [0.05] * 4), extents)
    assert dense.swept_bound_m == pytest.approx(0.05 * 0.11)
    assert dense.required_max_step_rad == pytest.approx(0.0093 / 0.11)
    assert dense.sufficient is (dense.swept_bound_m < 0.0093)


def test_max_joint_step_is_the_largest_per_step_delta() -> None:
    trajectory = ([0.0, 0.0], [0.1, 0.0], [0.1, 0.7])
    assert max_joint_step_rad(trajectory) == pytest.approx(0.7)


def test_single_waypoint_has_zero_step() -> None:
    assert max_joint_step_rad(([0.0, 0.0],)) == 0.0


def test_sparse_trajectory_is_refused(preflight_model: PreflightModel) -> None:
    extents = preflight_model.geometry_extents()
    # One giant 1.0 rad step at the max link radius sweeps far past any link thickness.
    sparse = (
        _neutral(preflight_model),
        preflight_model.qpos_from_arms((1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0), (0.0,) * _ARM),
    )
    assert not assess_density(sparse, extents).sufficient
    with pytest.raises(DensityInsufficientError):
        require_sufficient_density(sparse, extents)


def test_dense_trajectory_is_accepted(preflight_model: PreflightModel) -> None:
    extents = preflight_model.geometry_extents()
    dense = (
        preflight_model.qpos_from_arms((0.00,) + (0.0,) * 6, (0.0,) * _ARM),
        preflight_model.qpos_from_arms((0.02,) + (0.0,) * 6, (0.0,) * _ARM),
    )
    assessment = require_sufficient_density(dense, extents)
    assert assessment.sufficient


def test_preflight_refuses_a_sparse_collision_trajectory(preflight_model: PreflightModel) -> None:
    # Density (②) gates before the walk (①): a sparse trajectory is refused, never walked
    # to a vacuous "no collision".
    left = (-0.05, 0.09, 1.34, 2.26, -0.28, 0.06, -1.36)
    right = (-0.27, 1.06, -0.79, 1.14, 1.34, -0.42, -1.31)
    sparse = (
        _neutral(preflight_model),
        preflight_model.qpos_from_arms(left, right),
    )
    with pytest.raises(DensityInsufficientError):
        run_preflight(sparse)
