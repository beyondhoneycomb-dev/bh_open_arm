"""On-disk synthetic dataset builder for the WP-3D-02 copy-on-write edit tests.

The CoW edit engine runs the real `lerobot-edit-dataset` operations against a real
on-disk dataset, so these tests need one — built here from the WP-3A-06 fixtures
through the WP-3B-11 recorder embed (the mandated 3B test path), never a robot.

Each episode is given deliberately distinct content: a per-episode action offset and a
per-episode frame count, so the content hash that the sidecar remap joins on is unique
per episode. That is the normal case for recorded data (continuous streams never repeat)
and it makes the reverse lookup unambiguous, which is what the cross-check assertions
exercise.
"""

from __future__ import annotations

import logging
from pathlib import Path

from backend.recorder.embed.dataset import create_record_dataset
from backend.recorder.embed.loop import build_record_frame, frame_schema
from backend.recorder.quality.label import EpisodeLabel, Judgment, Provenance, Verdict
from backend.recorder.quality.sidecar import EpisodeSidecar, write_sidecar
from backend.recorder.quality.store import DatasetStore
from contracts.recorder import RecorderConfig, action_names, observation_state_names

FIXTURE_FPS = 30

# A per-episode action offset large enough that no two episodes share a frame value,
# so every episode hashes to a unique content identity.
_EPISODE_OFFSET = 1000.0


def _record_episode(dataset, schema, action_channels, state_channels, offset, frame_count, task):
    """Record one episode of distinct, deterministic content into a write-mode dataset.

    Args:
        dataset: The write-mode `LeRobotDataset`.
        schema: The frame schema.
        action_channels: The position-only action channel names.
        state_channels: The `observation.state` channel names.
        offset: The per-episode value offset that makes this episode's content unique.
        frame_count: The number of frames to record.
        task: The task label for the episode.
    """
    for frame_index in range(frame_count):
        value = offset + frame_index
        action = dict.fromkeys(action_channels, value)
        observation = dict.fromkeys(state_channels, value + 0.5)
        dataset.add_frame(build_record_frame(action, observation, task, schema))
    dataset.save_episode()


def build_dataset(
    root: Path, frame_counts: tuple[int, ...], repo_id: str = "synthetic/edit"
) -> str:
    """Build and finalize an on-disk multi-episode dataset with distinct-content episodes.

    Args:
        root: The directory the dataset is written under.
        frame_counts: The frame count of each episode, in order; its length is the
            episode count.
        repo_id: The base repository id.

    Returns:
        (str) The stamped repository id the dataset was written under.
    """
    config = RecorderConfig(bimanual=True, use_velocity_and_torque=True)
    schema = frame_schema(config)
    action_channels = action_names(config.bimanual)
    state_channels = observation_state_names(config.bimanual, config.use_velocity_and_torque)

    # lerobot's dataset ops log verbosely; suppress for the build only and always restore,
    # or the process-global disable leaks into later tests' warning-count assertions.
    logging.disable(logging.CRITICAL)
    try:
        dataset, stamped = create_record_dataset(repo_id, FIXTURE_FPS, config, root)
        for episode_index, frame_count in enumerate(frame_counts):
            _record_episode(
                dataset,
                schema,
                action_channels,
                state_channels,
                offset=episode_index * _EPISODE_OFFSET,
                frame_count=frame_count,
                task=f"task_{episode_index % 2}",
            )
        dataset.finalize()
        return stamped
    finally:
        logging.disable(logging.NOTSET)


def write_labels(root: Path, verdicts: tuple[Verdict, ...]) -> None:
    """Write one manual-verdict quality sidecar per episode.

    Args:
        root: The dataset root.
        verdicts: The manual verdict for each episode, in episode order.
    """
    store = DatasetStore(root)
    for episode_index, verdict in enumerate(verdicts):
        label = EpisodeLabel.judged(episode_index, manual=Judgment(verdict, Provenance.MANUAL))
        write_sidecar(store, EpisodeSidecar(episode_index=episode_index, label=label, report=None))
