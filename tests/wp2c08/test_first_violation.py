"""Acceptance ①: a collision trajectory yields the first violating waypoint + contact detail."""

from __future__ import annotations

from backend.collision_preflight.constants import (
    KNOWN_ARM_ARM_COLLISION_LEFT,
    KNOWN_ARM_ARM_COLLISION_RIGHT,
)
from backend.collision_preflight.model import PreflightModel
from backend.collision_preflight.preflight import run_preflight

_ARM_JOINT_COUNT = 7


def _interpolate(model: PreflightModel, steps: int) -> tuple[tuple[float, ...], ...]:
    """Dense trajectory from neutral toward the known arm-arm collision pose."""
    waypoints: list[tuple[float, ...]] = []
    for step in range(steps):
        fraction = step / (steps - 1)
        left = tuple(fraction * angle for angle in KNOWN_ARM_ARM_COLLISION_LEFT)
        right = tuple(fraction * angle for angle in KNOWN_ARM_ARM_COLLISION_RIGHT)
        waypoints.append(model.qpos_from_arms(left, right))
    return tuple(waypoints)


def _clean(model: PreflightModel) -> tuple[tuple[float, ...], ...]:
    """A short collision-free trajectory near neutral."""
    waypoints: list[tuple[float, ...]] = []
    for step in range(6):
        angle = 0.01 * step
        left = (angle, 0.0, 0.0, angle, 0.0, 0.0, 0.0)
        right = (-angle, 0.0, 0.0, angle, 0.0, 0.0, 0.0)
        waypoints.append(model.qpos_from_arms(left, right))
    return tuple(waypoints)


def test_clean_trajectory_passes(preflight_model: PreflightModel) -> None:
    result = run_preflight(_clean(preflight_model))
    assert result.ok
    assert result.first_violation is None
    assert result.waypoints_checked == 6


def test_collision_trajectory_reports_first_violation(preflight_model: PreflightModel) -> None:
    trajectory = _interpolate(preflight_model, 80)
    result = run_preflight(trajectory)

    assert not result.ok
    violation = result.first_violation
    assert violation is not None
    # The walk stops at the first violating waypoint.
    assert result.waypoints_checked == violation.waypoint_index + 1
    assert 0 <= violation.waypoint_index < len(trajectory)


def test_first_violation_carries_full_contact_detail(preflight_model: PreflightModel) -> None:
    result = run_preflight(_interpolate(preflight_model, 80))
    assert result.first_violation is not None
    contact = result.first_violation.contact

    # geom1/geom2/dist/pos/frame are all present and shaped (acceptance ①).
    assert contact.geom1 and contact.geom2
    assert contact.geom1 != contact.geom2
    assert isinstance(contact.dist_m, float)
    assert len(contact.pos) == 3
    assert len(contact.frame) == 9
    # Within margin means the separation is below the honoured buffer.
    assert contact.dist_m < result.margin.margin_m


def test_earlier_violation_wins_over_later(preflight_model: PreflightModel) -> None:
    # A denser sampling cannot move the first violation later along the same path.
    coarse = run_preflight(_interpolate(preflight_model, 40))
    fine = run_preflight(_interpolate(preflight_model, 80))
    assert coarse.first_violation is not None
    assert fine.first_violation is not None
    coarse_fraction = coarse.first_violation.waypoint_index / 39
    fine_fraction = fine.first_violation.waypoint_index / 79
    assert fine_fraction <= coarse_fraction + 0.05
