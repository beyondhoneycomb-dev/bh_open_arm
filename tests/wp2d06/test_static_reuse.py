"""Single-source reuse and the linear residual note (WP-2D-06 ④ and reuse mandate)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

import backend.replay.preverify as preverify_module
from backend.collision_preflight.preflight import run_preflight
from backend.replay.interpolate import interpolate_trajectory
from backend.replay.preverify import density_step_ceiling_rad, velocity_limits_rad_s
from backend.replay.waypoint import InterpolationMethod
from backend.safety_bringup.constants import (
    GRIPPER_SPEED_CLAMP_RAD_S,
    OCTOMAP_DEPRECATED_SYMBOLS,
)
from backend.safety_bringup.velocity import bootstrap_limiter_rad_s
from tests.wp2d06.fixtures import clear_sequence

VLIM = velocity_limits_rad_s()
CEIL = density_step_ceiling_rad()


def test_collision_check_is_the_reused_preflight_function() -> None:
    """The pre-verify calls WP-2C-08's run_preflight, not a second collision walk."""
    assert preverify_module.run_preflight is run_preflight


def test_velocity_ceiling_is_the_single_canon() -> None:
    """Arm velocity ceilings are the WP-1-06 bootstrap canon; the gripper is its register clamp."""
    np.testing.assert_allclose(VLIM[:7], bootstrap_limiter_rad_s())
    assert VLIM[7] == GRIPPER_SPEED_CLAMP_RAD_S


def test_linear_shows_residual_pollution_note() -> None:
    """The linear profile surfaces the residual-pollution note citing no acceleration limits."""
    traj = interpolate_trajectory(clear_sequence(InterpolationMethod.LINEAR), VLIM, CEIL)
    note = traj.residual_ui_note()
    assert note
    assert "has_acceleration_limits: false" in note
    assert "residual" in note


def test_smooth_profiles_show_no_residual_note() -> None:
    """Cubic and quintic zero the endpoint velocity, so they carry no residual-pollution note."""
    for method in (InterpolationMethod.CUBIC, InterpolationMethod.QUINTIC):
        traj = interpolate_trajectory(clear_sequence(method), VLIM, CEIL)
        assert traj.residual_ui_note() == ""


def test_source_holds_no_deprecated_environment_collision_tokens() -> None:
    """No replay source references the deprecated environment-collision symbols (FR-SAF-012)."""
    package = Path(preverify_module.__file__).parent
    for source in package.glob("*.py"):
        text = source.read_text(encoding="utf-8")
        for token in OCTOMAP_DEPRECATED_SYMBOLS:
            assert token not in text, f"{source.name} references {token!r}"
