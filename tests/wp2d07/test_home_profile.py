"""Acceptance ③ + profile validation: home = J4=π/2, never the J4=0 hardstop.

The default home is not invented here: it equals the committed asset's home keyframe and the
`openarm_driver` initial pose, and its limits are the reused `sim.ik` soft limits, not a
second copy. A profile that places an arm joint on a mechanical hardstop — J4=0 above all —
is refused rather than stored.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from backend.cartesian_jog.frames import KinematicFrames
from backend.home.constants import ARM_JOINT_COUNT, HOME_J4_ANGLE_RAD, J4_INDEX
from backend.home.profile import (
    HomeProfile,
    HomeProfileError,
    HomeProfileRegistry,
    default_home_profile,
    default_registry,
    limit_margins,
    validate_home_profile,
)
from sim.ik.limits import soft_limits


def test_default_home_is_j4_pi_over_2_not_zero() -> None:
    """③ The default home is J4=π/2, and its J4 is not the 0 hardstop."""
    profile = default_home_profile()
    assert profile.j4_angle_rad() == pytest.approx(math.pi / 2)
    assert profile.j4_angle_rad() != 0.0
    assert profile.q_urdf == (0.0, 0.0, 0.0, HOME_J4_ANGLE_RAD, 0.0, 0.0, 0.0, 0.0)
    assert profile.q_urdf[J4_INDEX] == pytest.approx(math.pi / 2)


def test_j4_zero_is_rejected_as_a_hardstop() -> None:
    """③ A profile at J4=0 is refused as a mechanical hardstop, not stored as a home."""
    hardstop_home = HomeProfile(name="j4_zero", q_urdf=(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0))
    with pytest.raises(HomeProfileError, match="hardstop"):
        validate_home_profile(hardstop_home)


def test_default_home_matches_committed_home_keyframe(frames: KinematicFrames) -> None:
    """③ The default home equals the committed asset's home keyframe (both arms), not a guess."""
    committed = np.asarray(frames.home_solution(), dtype=float)
    right = committed[: ARM_JOINT_COUNT + 1]
    left = committed[ARM_JOINT_COUNT + 1 :]
    default = np.asarray(default_home_profile().q_urdf, dtype=float)
    assert right == pytest.approx(default, abs=1e-5)
    assert left == pytest.approx(default, abs=1e-5)


def test_validation_reuses_sim_ik_soft_limits() -> None:
    """The hardstop check reads the same soft limits sim.ik writes into the model."""
    margins = limit_margins(default_home_profile())
    right_j4 = margins[J4_INDEX]
    reused = soft_limits("right")[J4_INDEX]
    assert right_j4.lower_rad == reused.lower_rad.value
    assert right_j4.upper_rad == reused.upper_rad.value
    # J4's lower bound is exactly the hardstop, which is why J4=0 is refused above.
    assert right_j4.lower_rad == 0.0


def test_gripper_closed_at_its_zero_boundary_is_allowed() -> None:
    """The gripper's closed position is its mechanical zero and is not treated as a hardstop."""
    margins = validate_home_profile(default_home_profile())
    gripper_margins = [margin for margin in margins if "finger" in margin.joint]
    assert gripper_margins
    assert all(not margin.at_hardstop for margin in gripper_margins)


def test_out_of_range_joint_is_rejected() -> None:
    """A joint outside its soft-limit range is refused."""
    over = HomeProfile(name="over", q_urdf=(5.0, 0.0, 0.0, HOME_J4_ANGLE_RAD, 0.0, 0.0, 0.0, 0.0))
    with pytest.raises(HomeProfileError):
        validate_home_profile(over)


def test_wrong_width_is_rejected() -> None:
    """A profile that is not eight values wide is refused."""
    with pytest.raises(HomeProfileError, match="values"):
        validate_home_profile(HomeProfile(name="short", q_urdf=(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)))


def test_registry_default_active_and_switching() -> None:
    """The registry serves the default active home and switches on request."""
    registry = default_registry()
    assert registry.active.name == "default"
    assert registry.names() == ("default",)

    lifted = HomeProfile(name="elbow_up", q_urdf=(0.0, 0.0, 0.0, 2.0, 0.0, 0.0, 0.0, 0.0))
    registry.register(lifted)
    assert registry.active.name == "default"
    registry.set_active("elbow_up")
    assert registry.active.name == "elbow_up"
    assert registry.get("elbow_up") is lifted


def test_registry_rejects_invalid_profile_on_register() -> None:
    """An invalid home cannot enter the registry."""
    registry = HomeProfileRegistry()
    with pytest.raises(HomeProfileError):
        registry.register(HomeProfile(name="bad", q_urdf=(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)))


def test_registry_unknown_name_raises() -> None:
    """Asking for or activating an unregistered name is an error, not a silent default."""
    registry = default_registry()
    with pytest.raises(HomeProfileError):
        registry.get("nope")
    with pytest.raises(HomeProfileError):
        registry.set_active("nope")
