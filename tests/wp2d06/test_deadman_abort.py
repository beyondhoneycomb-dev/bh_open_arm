"""Deadman release aborts the trajectory to a hold, reusing backend.deadman (WP-2D-06 ③)."""

from __future__ import annotations

from backend.deadman.monitor import DeadmanMonitor
from backend.replay import replay as replay_module
from backend.replay.replay import ReplayState, build_replay
from tests.wp2d06.fixtures import clear_sequence


def test_release_after_live_latches_to_hold() -> None:
    """A deadman that was live and then releases aborts immediately to HOLD."""
    executor = build_replay(clear_sequence())
    executor.start()
    for _ in range(10):
        executor.tick(deadman_released=False)
    frozen = executor.index
    executor.tick(deadman_released=True)
    assert executor.state is ReplayState.HOLD
    assert executor.index == frozen


def test_hold_is_not_resumed_by_deadman_returning() -> None:
    """Once aborted, a deadman coming back live does not resume the trajectory."""
    executor = build_replay(clear_sequence())
    executor.start()
    for _ in range(10):
        executor.tick(deadman_released=False)
    frozen = executor.index
    executor.tick(deadman_released=True)
    for _ in range(5):
        executor.tick(deadman_released=False)
    assert executor.state is ReplayState.HOLD
    assert executor.index == frozen


def test_released_before_ever_live_holds_without_advancing() -> None:
    """A deadman released before it was ever armed holds the cursor rather than moving."""
    executor = build_replay(clear_sequence())
    executor.start()
    for _ in range(5):
        sample = executor.tick(deadman_released=True)
        assert sample.index == 0
    # It has not latched: once the deadman goes live the replay proceeds.
    executor.tick(deadman_released=False)
    executor.tick(deadman_released=False)
    assert executor.index > 0
    assert executor.state is ReplayState.RUNNING


def test_reuses_backend_deadman_monitor() -> None:
    """The abort edge is backend.deadman.DeadmanMonitor, not a second latch implementation."""
    assert replay_module.DeadmanMonitor is DeadmanMonitor
    executor = build_replay(clear_sequence())
    # The executor holds a real DeadmanMonitor instance for the release edge.
    assert isinstance(executor._deadman, DeadmanMonitor)
