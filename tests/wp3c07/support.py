"""Shared builders for the WP-3C-07 crash/resume drill tests.

The drill recovers the recorder's *output*, so these helpers first drive the committed
WP-3B-11 recorder over the synthetic `DummyRobot` fixture to produce a real on-disk v3.0
dataset, then build the crash-surviving journal that a resume restores from. The robot
and teleop adapters present the recorder loop's `RecordRobot`/`TeleopSource` shape over
the fixture, mirroring the WP-3B-11 tests without importing that WP's own test support.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from backend.crash_recovery.constants import JOURNAL_SCHEMA_VERSION
from backend.crash_recovery.journal import SessionJournal
from backend.recorder.embed import RecordEvents, RecordResult, RecordSpec, record_session
from contracts.fixtures.dummy_robot import DummyRobot
from contracts.recorder import action_names

FPS = 30
EPISODE_STEPS = 5
RESET_STEPS = 1
TASK = "grab"
BASE_REPO_ID = "synthetic/drill"


class DummyRobotAdapter:
    """Present the fixture `DummyRobot` as the recorder loop's `RecordRobot`."""

    def __init__(self, bimanual: bool, use_velocity_and_torque: bool) -> None:
        """Wrap a fresh `DummyRobot` at the zero pose."""
        self.mRobot = DummyRobot(bimanual=bimanual, use_velocity_and_torque=use_velocity_and_torque)

    def observe(self) -> Mapping[str, float]:
        """Return the current `observation.state`, keyed by channel name."""
        observation = self.mRobot.observation()
        names: tuple[str, ...] = observation["names"]  # type: ignore[assignment]
        state: tuple[float, ...] = observation["observation.state"]  # type: ignore[assignment]
        return dict(zip(names, state, strict=True))

    def send_action(self, action: Mapping[str, float]) -> None:
        """Apply a position-only action, advancing the robot one tick."""
        self.mRobot.step(action)


class RampTeleop:
    """A deterministic position-only action source: every channel ramps by one per call."""

    def __init__(self, bimanual: bool) -> None:
        """Start the ramp at zero over the position-only channel names."""
        self.mNames = action_names(bimanual)
        self.mStep = 0

    def get_action(self) -> Mapping[str, float]:
        """Return `{<motor>.pos: step}` for the current step and advance the ramp."""
        action = dict.fromkeys(self.mNames, float(self.mStep))
        self.mStep += 1
        return action


def build_baseline_dataset(root: Path, num_episodes: int) -> RecordResult:
    """Record a real state/action dataset of `num_episodes` complete episodes.

    Args:
        root: The dataset root to write.
        num_episodes: How many complete episodes to record.

    Returns:
        (RecordResult) The recorder's result, carrying the stamped `repo_id`.
    """
    spec = RecordSpec(
        repo_id=BASE_REPO_ID,
        single_task=TASK,
        fps=FPS,
        bimanual=False,
        use_velocity_and_torque=False,
        num_episodes=num_episodes,
        episode_steps=EPISODE_STEPS,
        reset_steps=RESET_STEPS,
    )
    return record_session(
        spec, DummyRobotAdapter(False, False), RampTeleop(False), RecordEvents(), root
    )


def make_journal(result: RecordResult, session_target_episodes: int) -> SessionJournal:
    """Build the crash-surviving journal for a recorded session.

    Args:
        result: The recorder result whose stamped id and saved count are journaled.
        session_target_episodes: The episode target the session was aiming for (larger
            than the saved count when the crash interrupted it).

    Returns:
        (SessionJournal) The journal a resume restores from.
    """
    return SessionJournal(
        schema_version=JOURNAL_SCHEMA_VERSION,
        stamped_repo_id=result.repo_id,
        single_task=TASK,
        saved_episodes=result.saved_episodes,
        fps=FPS,
        bimanual=False,
        use_velocity_and_torque=False,
        num_episodes=session_target_episodes,
        episode_steps=EPISODE_STEPS,
        reset_steps=RESET_STEPS,
    )
