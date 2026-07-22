"""Replay lifecycle: start, step, pause/resume, abort, dwell, gripper (WP-2D-06)."""

from __future__ import annotations

import pytest

from backend.replay.replay import ReplayState, build_replay
from tests.wp2d06.fixtures import clear_sequence


def _run_to_done(executor, max_ticks: int = 2000) -> int:
    """Tick a running executor to completion, returning the tick count."""
    ticks = 0
    while not executor.done and ticks < max_ticks:
        executor.tick()
        ticks += 1
    return ticks


def test_start_then_run_to_done() -> None:
    """A started replay steps from sample zero to DONE at the last sample."""
    executor = build_replay(clear_sequence())
    first = executor.start()
    assert executor.state is ReplayState.RUNNING
    assert first.index == 0
    _run_to_done(executor)
    assert executor.state is ReplayState.DONE
    assert executor.index == executor.sample_count - 1


def test_pause_holds_then_resume_advances() -> None:
    """Pause freezes the cursor; resume advances again."""
    executor = build_replay(clear_sequence())
    executor.start()
    for _ in range(10):
        executor.tick()
    held_index = executor.index
    executor.pause()
    assert executor.state is ReplayState.PAUSED
    for _ in range(5):
        assert executor.tick().index == held_index
    executor.resume()
    executor.tick()
    assert executor.index == held_index + 1


def test_abort_latches_to_hold() -> None:
    """Abort stops immediately and holds; further ticks do not advance."""
    executor = build_replay(clear_sequence())
    executor.start()
    for _ in range(10):
        executor.tick()
    held_index = executor.index
    executor.abort()
    assert executor.state is ReplayState.HOLD
    assert executor.held
    for _ in range(5):
        assert executor.tick().index == held_index


def test_start_refused_after_terminal_state() -> None:
    """A held (aborted) executor cannot be restarted without a fresh build."""
    executor = build_replay(clear_sequence())
    executor.start()
    executor.abort()
    with pytest.raises(RuntimeError, match="terminal state"):
        executor.start()


def test_gripper_command_is_present_in_samples() -> None:
    """Each commanded sample carries the interpolated gripper value."""
    executor = build_replay(clear_sequence())
    sample = executor.start()
    assert sample.gripper == pytest.approx(-0.2)
    assert sample.arm_side == "right"
    assert len(sample.q_arm) == 7


def test_dwell_holds_the_configuration() -> None:
    """A dwell holds the same commanded configuration across consecutive ticks."""
    executor = build_replay(clear_sequence())
    start = executor.start()
    # The first waypoint dwells 0.1 s (five held samples) before the first segment moves.
    for _ in range(5):
        held = executor.tick()
        assert held.q_arm == start.q_arm
