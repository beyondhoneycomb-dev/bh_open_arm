"""Acceptance ③ — the repulsion torque stays within the URDF effort, always.

The wall engages only within 5 deg of a limit, pushes toward the interior, and saturates at a
cap that is a fraction of the URDF effort. A cap built over that effort is refused at
construction — the `02b` §4.2 WP-2D-04 FAIL_BLOCKING branch — not clamped in flight.
"""

from __future__ import annotations

import pytest

pytest.importorskip("mujoco")

from backend.freedrive_walls import (
    JointLimitRepulsion,
    JointWall,
    RepulsionEffortExceededError,
    build_arm_repulsion,
)
from backend.freedrive_walls.constants import URDF_EFFORT_LIMIT_NM
from backend.freedrive_walls.errors import FreedriveConfigError
from tests.wp2d04._fixtures import (
    SYNTHETIC_EFFORT_NM,
    SYNTHETIC_LOWER_RAD,
    SYNTHETIC_UPPER_RAD,
    synthetic_repulsion,
)

_BAND_RAD = 0.0873


def test_interior_pose_has_zero_repulsion() -> None:
    """A pose far from every limit contributes no wall torque."""
    rep = synthetic_repulsion()
    torque = rep.repulsion_torque([0.0] * rep.count)
    assert all(entry.value == 0.0 for entry in torque)


def test_near_upper_limit_pushes_toward_interior() -> None:
    """Within the band of the upper limit the torque is negative and below the cap."""
    rep = synthetic_repulsion(fraction=0.5, band_rad=_BAND_RAD)
    q = [0.0] * rep.count
    q[0] = SYNTHETIC_UPPER_RAD[0] - _BAND_RAD / 2.0  # halfway into the band
    torque = rep.repulsion_torque(q)
    assert torque[0].value < 0.0
    assert abs(torque[0].value) <= 0.5 * SYNTHETIC_EFFORT_NM[0]


def test_near_lower_limit_pushes_toward_interior() -> None:
    """Within the band of the lower limit the torque is positive."""
    rep = synthetic_repulsion(fraction=0.5, band_rad=_BAND_RAD)
    q = [0.0] * rep.count
    q[3] = SYNTHETIC_LOWER_RAD[3] + _BAND_RAD / 2.0
    assert rep.repulsion_torque(q)[3].value > 0.0


def test_past_limit_saturates_at_the_cap() -> None:
    """An over-limit angle saturates at the cap, never past it."""
    rep = synthetic_repulsion(fraction=0.5, band_rad=_BAND_RAD)
    q = [0.0] * rep.count
    q[4] = SYNTHETIC_UPPER_RAD[4] + 10.0  # far past the limit
    assert rep.repulsion_torque(q)[4].value == pytest.approx(-0.5 * SYNTHETIC_EFFORT_NM[4])


def test_repulsion_never_exceeds_effort_anywhere() -> None:
    """Across a sweep from below the lower limit to above the upper, no joint exceeds effort."""
    rep = synthetic_repulsion(fraction=1.0, band_rad=_BAND_RAD)
    steps = 40
    for joint in range(rep.count):
        span = SYNTHETIC_UPPER_RAD[joint] - SYNTHETIC_LOWER_RAD[joint]
        for step in range(steps + 1):
            q = [0.0] * rep.count
            q[joint] = SYNTHETIC_LOWER_RAD[joint] - span + step * (3.0 * span / steps)
            torque = rep.repulsion_torque(q)
            assert abs(torque[joint].value) <= SYNTHETIC_EFFORT_NM[joint] + 1e-9


def test_cap_over_effort_is_fail_blocking() -> None:
    """A wall whose cap exceeds the joint effort is refused at construction (FAIL_BLOCKING)."""
    walls = [JointWall(-1.0, 1.0, 7.0, 8.0)]  # cap 8 Nm over a 7 Nm effort
    with pytest.raises(RepulsionEffortExceededError) as excinfo:
        JointLimitRepulsion(walls, _BAND_RAD)
    assert excinfo.value.joint_index == 0
    assert excinfo.value.effort_nm == 7.0


def test_fraction_above_one_is_refused() -> None:
    """A repulsion effort fraction above 1.0 would exceed effort, so it is refused."""
    with pytest.raises(FreedriveConfigError):
        build_arm_repulsion("right", fraction=1.5)


def test_build_arm_repulsion_caps_within_effort() -> None:
    """The reused-limits arm field caps every joint within the canonical URDF effort."""
    pytest.importorskip("lerobot")
    rep = build_arm_repulsion("right", fraction=0.5)
    assert rep.count == len(URDF_EFFORT_LIMIT_NM)
    # Deep past every limit saturates each joint at its cap, which must be within effort.
    saturating = [upper + 5.0 for upper in rep.upper_bounds()]
    torque = rep.repulsion_torque(saturating)
    for entry, effort in zip(torque, URDF_EFFORT_LIMIT_NM, strict=True):
        assert abs(entry.value) <= effort
        assert abs(entry.value) == pytest.approx(0.5 * effort)
