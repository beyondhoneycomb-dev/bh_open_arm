"""The session-end stop posture equals the home and rides the same guarded path.

`04` §3.5 records the driver's stop posture as identical to its initial/home pose, so the
session-end stop is the home under its own name — pre-verified and non-auto-running exactly
as a home return is, and never the J4=0 hardstop.
"""

from __future__ import annotations

import math

import pytest

from backend.home.homereturn import HomeReturn, HomeReturnBlockedError
from backend.home.profile import default_home_profile, session_stop_profile
from tests.wp2d07.conftest import COLLIDING_START, SAFE_START


def test_session_stop_equals_home() -> None:
    """The stop posture is the home posture, at J4=π/2 and not the J4=0 hardstop."""
    stop = session_stop_profile()
    assert stop.q_urdf == default_home_profile().q_urdf
    assert stop.j4_angle_rad() == pytest.approx(math.pi / 2)
    assert stop.j4_angle_rad() != 0.0


def test_session_stop_plan_is_pre_verified(home: HomeReturn) -> None:
    """A clear path to the stop posture is executable through the same pre-verify."""
    plan = home.plan_session_stop(SAFE_START)
    assert plan.preview.profile_name == "session_stop"
    assert plan.executable is True
    right_traj, left_traj = plan.executable_trajectory()
    assert len(right_traj) > 1


def test_session_stop_honours_the_no_auto_run_guard(home: HomeReturn) -> None:
    """A failed pre-verify blocks the session-end stop just as it blocks a home return."""
    plan = home.plan_session_stop(COLLIDING_START)
    assert plan.executable is False
    assert plan.requires_waypoint is True
    with pytest.raises(HomeReturnBlockedError):
        plan.executable_trajectory()
