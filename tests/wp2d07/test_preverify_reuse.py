"""The pre-verify is WP-2D-06's four-check walk reused, which itself reuses WP-2C-08.

Evidence the reuse is real and not re-implemented: the home pre-verify calls the identical
`backend.replay` symbols (`run_pre_verify`, `interpolate_trajectory`); its collision half is
WP-2C-08's `run_preflight`; and the density ceiling and velocity limits come from their single
canonical sources, not a copy here. The home band adds no interpolator or collision walk of
its own.
"""

from __future__ import annotations

import backend.home.preverify as home_preverify
import backend.replay as replay
from backend.home.preverify import HomePreflight
from backend.home.profile import default_home_profile
from tests.wp2d07.conftest import COLLIDING_START, HOME_ARM, SAFE_START


def test_preverify_uses_the_wp2d06_symbols() -> None:
    """The home pre-verify calls the one WP-2D-06 interpolator and four-check walk."""
    assert home_preverify.run_pre_verify is replay.run_pre_verify
    assert home_preverify.interpolate_trajectory is replay.interpolate_trajectory
    assert home_preverify.velocity_limits_rad_s is replay.velocity_limits_rad_s
    assert home_preverify.density_step_ceiling_rad is replay.density_step_ceiling_rad


def test_collision_half_is_wp2c08_run_preflight() -> None:
    """WP-2D-06's collision check — reused by the home pre-verify — is WP-2C-08's run_preflight."""
    import backend.collision_preflight as collision_preflight

    assert replay.preverify.run_preflight is collision_preflight.run_preflight


def test_density_ceiling_is_the_reused_wp2c08_geometry_bound(preflight: HomePreflight) -> None:
    """The home density ceiling is WP-2C-08's geometry bound, taken from WP-2D-06's helper."""
    assert preflight.density_step_ceiling_rad == replay.density_step_ceiling_rad()


def test_safe_home_leg_passes_all_four_checks(preflight: HomePreflight) -> None:
    """A safe leg to home clears limit, velocity, and both collision checks."""
    start_right = SAFE_START[:7]
    _, verdict = preflight.preverify_leg(
        "right",
        start_right,
        [],
        HOME_ARM,
        default_home_profile().gripper(),
        other_arm_hold=HOME_ARM,
    )
    assert verdict.ok is True
    assert verdict.category is None
    # The reused WP-2C-08 preflight ran its self-collision activation proof.
    assert verdict.collision.self_collision.arm_arm_contact_count > 0


def test_colliding_leg_reports_the_first_violating_sample(preflight: HomePreflight) -> None:
    """A within-limits self-colliding leg is caught by the reused collision walk at sample 0."""
    start_right = COLLIDING_START[:7]
    _, verdict = preflight.preverify_leg(
        "right",
        start_right,
        [],
        HOME_ARM,
        default_home_profile().gripper(),
        other_arm_hold=HOME_ARM,
    )
    assert verdict.ok is False
    assert verdict.category is not None
    assert verdict.category.value == "self_collision"
    assert verdict.first_violation_index == 0
