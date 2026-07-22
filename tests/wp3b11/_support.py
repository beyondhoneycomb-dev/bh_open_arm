"""Synthetic robot/teleop/dataset stand-ins for the WP-3B-11 recorder tests.

The embed drives a robot it does not have, so these adapters present the loop's
`RecordRobot`/`TeleopSource` shape over the frozen fixtures — the `DummyRobot`
(position-only in, interleaved `observation.state` out) and a deterministic action
ramp. A fake dataset counts `finalize` calls so a test can prove the embed's
`finally` fired without a real parquet write, and an exploding robot injects an
exception or an interruption mid-loop.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from backend.recorder.embed import RecordEvents
from contracts.fixtures.dummy_robot import DummyRobot
from contracts.recorder import action_names


class DummyRobotAdapter:
    """Present the fixture `DummyRobot` as the loop's `RecordRobot`.

    `observe()` reads the current interleaved state as `{channel: value}` without
    advancing the robot; `send_action()` applies the position-only action, which
    advances the first-order dynamics one tick.
    """

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


class RerecordOnceTeleop:
    """A ramp that requests a re-record exactly once, after a fixed number of frames.

    The re-record is fired from inside `get_action` to model a GUI re-record button
    pressed mid-episode; the fired flag keeps it to a single episode so the second
    pass records to completion.
    """

    def __init__(self, bimanual: bool, events: RecordEvents, fire_after: int) -> None:
        """Wrap a ramp with a one-shot re-record trigger at `fire_after` calls."""
        self.mRamp = RampTeleop(bimanual)
        self.mEvents = events
        self.mFireAfter = fire_after
        self.mCalls = 0
        self.mFired = False

    def get_action(self) -> Mapping[str, float]:
        """Return the next ramp action, firing one re-record when the count is reached."""
        action = self.mRamp.get_action()
        self.mCalls += 1
        if not self.mFired and self.mCalls >= self.mFireAfter:
            self.mEvents.request_rerecord()
            self.mFired = True
        return action


class ExplodingRobot:
    """A robot whose `observe()` raises a chosen exception on the Nth call.

    Used to inject an exception and a `KeyboardInterrupt` into the record loop so a
    test can prove `finalize()` still runs on those exit paths.
    """

    def __init__(self, inner: DummyRobotAdapter, fail_on_call: int, error: BaseException) -> None:
        """Fail on the `fail_on_call`-th observe with `error`; delegate otherwise."""
        self.mInner = inner
        self.mFailOnCall = fail_on_call
        self.mError = error
        self.mCalls = 0

    def observe(self) -> Mapping[str, float]:
        """Return the delegate's observation, or raise on the configured call."""
        self.mCalls += 1
        if self.mCalls >= self.mFailOnCall:
            raise self.mError
        return self.mInner.observe()

    def send_action(self, action: Mapping[str, float]) -> None:
        """Delegate the action to the inner robot."""
        self.mInner.send_action(action)


class FakeDataset:
    """A minimal `LeRobotDataset` stand-in that counts control calls.

    It carries only what the session touches — an `fps`, frame/save/clear/finalize
    calls — so a test can assert the exact control flow (finalize ran, the buffer
    was cleared, no save happened) without a real parquet write.
    """

    def __init__(self, fps: int) -> None:
        """Start an empty write-mode fake at the given frame rate."""
        self.fps = fps
        self.mPending: list[dict[str, Any]] = []
        self.finalize_calls = 0
        self.save_calls = 0
        self.clear_calls = 0
        self.saved_episode_sizes: list[int] = []

    def add_frame(self, frame: dict[str, Any]) -> None:
        """Buffer one frame."""
        self.mPending.append(frame)

    def save_episode(self) -> None:
        """Record the buffered episode and reset the buffer."""
        self.save_calls += 1
        self.saved_episode_sizes.append(len(self.mPending))
        self.mPending = []

    def clear_episode_buffer(self) -> None:
        """Discard the buffered episode without recording it."""
        self.clear_calls += 1
        self.mPending = []

    def finalize(self) -> None:
        """Count a finalize; idempotent, like the real dataset."""
        self.finalize_calls += 1
