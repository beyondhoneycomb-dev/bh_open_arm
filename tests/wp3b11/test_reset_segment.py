"""The environment-reset segment: unrecorded, but still under teleoperation.

Between episodes the loop runs once more with `dataset=None`: the teleop keeps
producing actions and the robot keeps being driven so the scene can be reset, and
not one frame of it is written. This proves both halves — the reset drives teleop
and robot exactly `reset_steps` extra times, and adds zero frames.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest

import backend.recorder.embed.session as session_mod
from backend.recorder.embed import RecordEvents, RecordSpec, record_session

from ._support import DummyRobotAdapter, FakeDataset, RampTeleop

FPS = 30
EPISODE_STEPS = 4
RESET_STEPS = 3
NUM_EPISODES = 2


class _CountingTeleop:
    """A ramp that counts how many actions it produced."""

    def __init__(self, bimanual: bool) -> None:
        self.mRamp = RampTeleop(bimanual)
        self.calls = 0

    def get_action(self) -> Mapping[str, float]:
        self.calls += 1
        return self.mRamp.get_action()


class _CountingRobot:
    """A robot adapter that counts how many actions it was driven with."""

    def __init__(self, bimanual: bool, use_velocity_and_torque: bool) -> None:
        self.mInner = DummyRobotAdapter(bimanual, use_velocity_and_torque)
        self.send_calls = 0

    def observe(self) -> Mapping[str, float]:
        return self.mInner.observe()

    def send_action(self, action: Mapping[str, float]) -> None:
        self.send_calls += 1
        self.mInner.send_action(action)


def test_reset_drives_teleop_and_robot_without_recording(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """One reset runs after the first of two episodes: teleop kept, zero frames added."""
    fake = FakeDataset(fps=FPS)
    monkeypatch.setattr(
        session_mod, "create_record_dataset", lambda *_a, **_k: (fake, "synthetic/reset_stamped")
    )
    teleop = _CountingTeleop(bimanual=True)
    robot = _CountingRobot(bimanual=True, use_velocity_and_torque=True)
    spec = RecordSpec(
        repo_id="synthetic/reset",
        single_task="grab",
        fps=FPS,
        bimanual=True,
        use_velocity_and_torque=True,
        num_episodes=NUM_EPISODES,
        episode_steps=EPISODE_STEPS,
        reset_steps=RESET_STEPS,
    )

    record_session(spec, robot, teleop, RecordEvents(), tmp_path)

    recorded_steps = NUM_EPISODES * EPISODE_STEPS
    # Exactly one reset segment runs (after all episodes but the last).
    driven_steps = recorded_steps + RESET_STEPS
    assert teleop.calls == driven_steps
    assert robot.send_calls == driven_steps
    # Only the recorded steps became frames — the reset added none.
    assert sum(fake.saved_episode_sizes) == recorded_steps
    assert fake.save_calls == NUM_EPISODES
