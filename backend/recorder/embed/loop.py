"""The in-process record loop and the frame it builds (WP-3B-11).

This is the embedded equivalent of `lerobot_record.record_loop()`: the observe →
act → send → add-frame cycle, run in *this* process rather than by spawning the
`lerobot record` console script. Two things it deliberately keeps from the
original and one it deliberately drops:

- kept: the `events`-driven early exit (read-and-clear at the top of the loop),
  and the `dataset.fps == fps` guard that refuses a mismatched frame rate before
  a single frame is written (WP-3B-11 acceptance ⑦).
- kept: a `dataset=None` pass runs the full cycle — teleop is read, the robot is
  driven — but writes no frame. That is the environment-reset segment, recorded
  by nobody yet still under teleoperation.
- dropped: the wall-clock `precise_sleep` pacing. Against a synthetic robot there
  is no real actuator to pace, so the loop is bounded by a frame budget rather
  than an elapsed-time budget, which keeps an offline run deterministic.

The frame's `action` is built from the position-only channel names alone
(`action_names`, every one a `.pos`), so a `.vel`/`.torque` value in the teleop
action can never reach an `action` dimension — the `CTR-REC@v1` FAIL_BLOCKING rule
holds by construction, not by a downstream check.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np
import numpy.typing as npt

from backend.recorder.embed.constants import TASK_KEY
from backend.recorder.embed.events import RecordEvents
from contracts.recorder import (
    ACTION_KEY,
    OBSERVATION_STATE_KEY,
    RecorderConfig,
    action_names,
    observation_state_names,
)


class RecorderFpsMismatchError(ValueError):
    """Raised when the record loop's fps does not equal the dataset's own fps.

    LeRobot writes one `fps` into the dataset metadata and paces the loop at
    another only if they agree; a mismatch silently mislabels every timestamp, so
    the loop refuses it up front (WP-3B-11 acceptance ⑦).
    """


class TeleopSource(Protocol):
    """A source of position-only actions — a teleoperator, in `record_loop` terms.

    The one method mirrors `Teleoperator.get_action()`: it returns the commanded
    joint positions as `{<motor>.pos: degrees}`. It is the seam the VR teleop
    (`WP-3B-07`..`10`) and the KER teleop (`WP-3B-14`) plug into; the embed depends
    on the shape, never on which device produced it.
    """

    def get_action(self) -> Mapping[str, float]:
        """Return the position-only action for this step, keyed `<motor>.pos`."""
        ...


class RecordRobot(Protocol):
    """The robot the loop observes and drives, in `record_loop` terms.

    `observe()` is `Robot.get_observation()` reduced to the recorded state vector
    (`{channel_name: value}` over `observation.state` names); `send_action()` is
    `Robot.send_action()`. The observation is read *before* the action is sent, so
    a recorded frame pairs the pre-action state with the action that was applied —
    the LeRobot ordering.
    """

    def observe(self) -> Mapping[str, float]:
        """Return the current `observation.state`, keyed by channel name."""
        ...

    def send_action(self, action: Mapping[str, float]) -> None:
        """Apply a position-only action to the robot."""
        ...


@dataclass(frozen=True)
class FrameSchema:
    """The channel names a frame's `action` and `observation.state` vectors carry.

    Attributes:
        action_channels: The position-only `action` names, in dataset order; every
            one a `.pos` channel, which is what keeps `action` position-only.
        state_channels: The interleaved `observation.state` names, in dataset order.
    """

    action_channels: tuple[str, ...]
    state_channels: tuple[str, ...]


def frame_schema(config: RecorderConfig) -> FrameSchema:
    """Derive the frame channel names from a frozen `CTR-REC@v1` configuration.

    Args:
        config: The recorder configuration.

    Returns:
        (FrameSchema) The position-only action names and the interleaved state names.
    """
    return FrameSchema(
        action_channels=action_names(config.bimanual),
        state_channels=observation_state_names(config.bimanual, config.use_velocity_and_torque),
    )


def build_record_frame(
    action: Mapping[str, float],
    observation: Mapping[str, float],
    single_task: str,
    schema: FrameSchema,
) -> dict[str, Any]:
    """Assemble one `LeRobotDataset.add_frame` frame, position-only by construction.

    The `action` vector is read from `schema.action_channels` only — all `.pos`
    names — so a `.vel`/`.torque` key present in `action` is never sampled into an
    `action` dimension (`CTR-REC@v1`, `07` §2.3.3). The `observation.state` vector
    keeps velocity and torque, addressed by the interleaved names.

    Args:
        action: The commanded position-only action, keyed `<motor>.pos`.
        observation: The current state, keyed by `observation.state` channel name.
        single_task: The task label attached to the frame.
        schema: The channel names both vectors are built over.

    Returns:
        (dict) A frame with `action`, `observation.state` and the `task` label.
    """
    action_vector: npt.NDArray[np.float32] = np.array(
        [float(action[name]) for name in schema.action_channels], dtype=np.float32
    )
    state_vector: npt.NDArray[np.float32] = np.array(
        [float(observation[name]) for name in schema.state_channels], dtype=np.float32
    )
    return {ACTION_KEY: action_vector, OBSERVATION_STATE_KEY: state_vector, TASK_KEY: single_task}


def record_loop(
    robot: RecordRobot,
    teleop: TeleopSource,
    events: RecordEvents,
    fps: int,
    max_steps: int,
    single_task: str,
    schema: FrameSchema,
    dataset: Any = None,
) -> int:
    """Run one observe→act→send→record segment in-process, events-driven.

    With `dataset` set the segment records: each step reads the state, gets an
    action, drives the robot, and adds a frame. With `dataset=None` the same cycle
    runs but no frame is written — the environment-reset segment, under teleop but
    unrecorded. The segment ends when the frame budget is spent or an early exit is
    requested, whichever comes first.

    Args:
        robot: The robot to observe and drive.
        teleop: The position-only action source.
        events: The backend-owned `RecordEvents`; its early-exit flag is read and
            cleared at the top of each step.
        fps: The loop frame rate; must equal `dataset.fps` when recording.
        max_steps: The frame budget for this segment.
        single_task: The task label for recorded frames.
        schema: The channel names frames are built over.
        dataset: The `LeRobotDataset` to record into, or None for a reset segment.

    Returns:
        (int) The number of steps run (frames written, when recording).

    Raises:
        RecorderFpsMismatchError: When recording and `dataset.fps != fps`.
    """
    if dataset is not None and dataset.fps != fps:
        raise RecorderFpsMismatchError(
            f"record loop fps {fps} does not equal dataset fps {dataset.fps}; "
            "a mismatched rate mislabels every recorded timestamp"
        )
    steps = 0
    while steps < max_steps:
        if events.take_exit_early():
            break
        observation = robot.observe()
        action = teleop.get_action()
        robot.send_action(action)
        if dataset is not None:
            dataset.add_frame(build_record_frame(action, observation, single_task, schema))
        steps += 1
    return steps
