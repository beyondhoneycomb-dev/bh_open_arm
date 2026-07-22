"""No pre-verify bypass path exists — the FAIL_BLOCKING guard (WP-2D-06 ①)."""

from __future__ import annotations

import inspect

import pytest

import backend.replay.replay as replay_module
from backend.replay.preverify import PreVerifyCategory, run_pre_verify
from backend.replay.replay import PreVerifyError, ReplayExecutor, build_replay
from tests.wp2d06.fixtures import CLEAR_START, SELF_COLLISION_END, clear_sequence, two_point


def test_build_replay_refuses_a_failing_trajectory() -> None:
    """A colliding trajectory raises rather than returning a runnable executor."""
    with pytest.raises(PreVerifyError) as excinfo:
        build_replay(two_point(CLEAR_START, SELF_COLLISION_END))
    assert excinfo.value.result.category is PreVerifyCategory.SELF_COLLISION
    assert excinfo.value.result.first_violation_index is not None


def test_build_replay_returns_executor_for_clear_trajectory() -> None:
    """A clear trajectory yields a ready executor."""
    executor = build_replay(clear_sequence())
    assert isinstance(executor, ReplayExecutor)


def test_executor_constructor_rejects_non_ok_result() -> None:
    """The executor cannot be constructed from a failing pre-verify — no forged-verdict path."""
    from backend.replay.interpolate import interpolate_trajectory
    from backend.replay.preverify import density_step_ceiling_rad, velocity_limits_rad_s

    traj = interpolate_trajectory(
        two_point(CLEAR_START, SELF_COLLISION_END),
        velocity_limits_rad_s(),
        density_step_ceiling_rad(),
    )
    failing = run_pre_verify(traj)
    assert not failing.ok
    with pytest.raises(PreVerifyError):
        ReplayExecutor(traj, failing)


def test_build_replay_is_the_only_public_entry() -> None:
    """`build_replay` is the sole module function that constructs an executor.

    Any other function that returned a ReplayExecutor would be a second entry that could skip
    the pre-verify; the module exposes exactly one.
    """
    builders = [
        name
        for name, obj in inspect.getmembers(replay_module, inspect.isfunction)
        if not name.startswith("_")
        and "ReplayExecutor" in str(inspect.signature(obj).return_annotation)
    ]
    assert builders == ["build_replay"]
