"""The in-process recording session: episodes, re-record, reset, guaranteed finalize.

This is the embedded equivalent of `lerobot_record.record()` — the multi-episode
loop around `record_loop()` — reduced to the recorder invariants WP-3B-11 stakes
its acceptance on and lifted off the robot hardware onto the synthetic fixtures:

- **finalize on every exit path.** `finalize()` writes the parquet footer; without
  it the whole dataset is invalid (`02b` §6.2 WP-3B-11). So it runs in a `finally`,
  and it is the *first* statement there — no teardown step can throw and skip it —
  and it is idempotent. Normal return, an exception raised inside the loop, and a
  `KeyboardInterrupt` all pass through that `finally` (acceptance ③/④).
- **re-record does not advance the episode index.** A re-record clears the episode
  buffer and `continue`s without `save_episode()`, so the discarded episode is
  never counted and the next saved episode keeps the index the cleared one would
  have had (acceptance ④). `save_episode()` is the only thing that advances it.
- **the reset segment is unrecorded but teleoperated.** Between episodes the loop
  runs once more with `dataset=None`: teleop keeps driving the robot to reset the
  scene, and not one frame of it is written (`FR-REC` reset semantics).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.recorder.embed.dataset import create_record_dataset
from backend.recorder.embed.events import RecordEvents
from backend.recorder.embed.loop import (
    RecordRobot,
    TeleopSource,
    frame_schema,
    record_loop,
)
from contracts.recorder import RecorderConfig


@dataclass(frozen=True)
class RecordSpec:
    """The knobs one recording session needs, over a frozen `CTR-REC@v1` config.

    Attributes:
        repo_id: The base repository id; stamped at creation.
        single_task: The task label attached to every recorded frame.
        fps: The recording frame rate; the loop refuses a dataset whose fps differs.
        bimanual: Two arms when True; fixes the action/state widths.
        use_velocity_and_torque: Whether `observation.state` carries `.vel`/`.torque`.
        num_episodes: How many episodes to save before the session ends.
        episode_steps: The frame budget of a recorded episode segment.
        reset_steps: The frame budget of the unrecorded environment-reset segment.
    """

    repo_id: str
    single_task: str
    fps: int
    bimanual: bool
    use_velocity_and_torque: bool
    num_episodes: int
    episode_steps: int
    reset_steps: int


@dataclass(frozen=True)
class RecordResult:
    """The outcome of a recording session.

    Attributes:
        repo_id: The stamped repository id the dataset was written under.
        root: The directory the dataset was written to.
        saved_episodes: How many episodes were saved (the final episode count).
        rerecorded_episodes: How many episodes were discarded and re-recorded.
    """

    repo_id: str
    root: Path
    saved_episodes: int
    rerecorded_episodes: int


def _needs_reset(saved_episodes: int, spec: RecordSpec, events: RecordEvents) -> bool:
    """Whether an environment-reset segment should run after the current episode.

    LeRobot resets after every episode except the last, and always before a
    re-record. The reset is skipped once the session is stopping.

    Args:
        saved_episodes: How many episodes have been saved so far.
        spec: The session spec.
        events: The backend-owned events.

    Returns:
        (bool) True when a reset segment should run.
    """
    if events.mStopRecording:
        return False
    more_to_record = saved_episodes < spec.num_episodes - 1
    return more_to_record or events.mRerecordEpisode


def record_session(
    spec: RecordSpec,
    robot: RecordRobot,
    teleop: TeleopSource,
    events: RecordEvents,
    root: Path,
) -> RecordResult:
    """Run a full recording session in-process, finalizing on every exit path.

    Args:
        spec: The session configuration.
        robot: The robot to observe and drive.
        teleop: The position-only action source.
        events: The backend-owned episode-control events.
        root: The directory the dataset is written under.

    Returns:
        (RecordResult) The stamped name, root, and saved/re-recorded episode counts.

    Raises:
        Exception: Anything raised inside the record loop propagates — after
            `finalize()` has run in the `finally`.
    """
    config = RecorderConfig(
        bimanual=spec.bimanual, use_velocity_and_torque=spec.use_velocity_and_torque
    )
    dataset, stamped_repo_id = create_record_dataset(spec.repo_id, spec.fps, config, root)
    schema = frame_schema(config)

    saved_episodes = 0
    rerecorded_episodes = 0
    try:
        while saved_episodes < spec.num_episodes and not events.mStopRecording:
            record_loop(
                robot=robot,
                teleop=teleop,
                events=events,
                fps=spec.fps,
                max_steps=spec.episode_steps,
                single_task=spec.single_task,
                schema=schema,
                dataset=dataset,
            )

            if _needs_reset(saved_episodes, spec, events):
                # Unrecorded, still teleoperated: dataset=None writes no frame.
                record_loop(
                    robot=robot,
                    teleop=teleop,
                    events=events,
                    fps=spec.fps,
                    max_steps=spec.reset_steps,
                    single_task=spec.single_task,
                    schema=schema,
                    dataset=None,
                )

            if events.mRerecordEpisode:
                events.mRerecordEpisode = False
                events.mExitEarly = False
                # Discard without saving: the episode index is NOT advanced.
                dataset.clear_episode_buffer()
                rerecorded_episodes += 1
                continue

            dataset.save_episode()
            saved_episodes += 1
    finally:
        # First and unconditional: the parquet footer must be written on the normal
        # path, on an exception, and on a KeyboardInterrupt alike. finalize() is
        # idempotent, so a second call from a caller or __del__ is harmless.
        dataset.finalize()

    return RecordResult(
        repo_id=stamped_repo_id,
        root=root,
        saved_episodes=saved_episodes,
        rerecorded_episodes=rerecorded_episodes,
    )
