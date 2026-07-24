"""On-disk dataset builder for the WP-3D-06 merge/split tests.

The verified merge and split run the real `lerobot-edit-dataset` operations against
real on-disk datasets, so these tests need them — built here from the WP-3B-11 recorder
embed (the mandated 3B test path), never a robot. Each episode is given distinct content
(a per-episode value offset) so its content hash is unique, which is what the sidecar
cross-check on a renumber joins on.

A dataset can be built under any `RecorderConfig` (so a velocity/torque-on 48-dim and a
velocity/torque-off 16-dim dataset can be produced for the shape-divergence test),
tagged with a gain profile, given a robot type, and labelled with per-episode quality
sidecars.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from backend.dataset.merge.constants import INFO_RELATIVE_PATH, INFO_ROBOT_TYPE_KEY
from backend.dataset.merge.gain import GainProfile, write_gain_profile
from backend.recorder.embed.dataset import create_record_dataset
from backend.recorder.embed.loop import build_record_frame, frame_schema
from backend.recorder.quality.label import EpisodeLabel, Judgment, Provenance, Verdict
from backend.recorder.quality.sidecar import EpisodeSidecar, write_sidecar
from backend.recorder.quality.store import DatasetStore
from contracts.recorder import RecorderConfig, action_names, observation_state_names

FIXTURE_FPS = 30

# A per-episode offset large enough that no two episodes share a frame value, so every
# episode hashes to a unique content identity across both merge sources.
_EPISODE_OFFSET = 1000.0

# A default follower PD gain tag for a compatible pair. The kp/kd widths are the eight
# per-arm motors (`03` §3.4 `lerobot_follower`); the values are in the DM MIT band.
DEFAULT_GAIN = GainProfile(
    profile_id="lerobot_follower",
    kp=(240.0, 240.0, 240.0, 240.0, 24.0, 31.0, 25.0, 25.0),
    kd=(5.0, 5.0, 3.0, 5.0, 0.3, 0.3, 0.3, 0.3),
)


def build_dataset(
    root: Path,
    frame_counts: tuple[int, ...],
    repo_id: str = "synthetic/merge",
    config: RecorderConfig | None = None,
    base_offset: float = 0.0,
) -> str:
    """Build and finalize an on-disk multi-episode dataset with distinct-content episodes.

    Args:
        root: The directory the dataset is written under.
        frame_counts: The frame count of each episode, in order; its length is the
            episode count.
        repo_id: The base repository id.
        config: The recorder configuration; defaults to bimanual, velocity/torque on.
        base_offset: An added offset so two sources never share episode content.

    Returns:
        (str) The stamped repository id the dataset was written under.
    """
    resolved = config or RecorderConfig(bimanual=True, use_velocity_and_torque=True)
    schema = frame_schema(resolved)
    action_channels = action_names(resolved.bimanual)
    state_channels = observation_state_names(resolved.bimanual, resolved.use_velocity_and_torque)

    logging.disable(logging.CRITICAL)
    try:
        dataset, stamped = create_record_dataset(repo_id, FIXTURE_FPS, resolved, root)
        for episode_index, frame_count in enumerate(frame_counts):
            offset = base_offset + episode_index * _EPISODE_OFFSET
            for frame_index in range(frame_count):
                value = offset + frame_index
                action = dict.fromkeys(action_channels, value)
                observation = dict.fromkeys(state_channels, value + 0.5)
                dataset.add_frame(
                    build_record_frame(action, observation, f"task_{episode_index % 2}", schema)
                )
            dataset.save_episode()
        dataset.finalize()
        return stamped
    finally:
        logging.disable(logging.NOTSET)


def tag_gain(root: Path, profile: GainProfile = DEFAULT_GAIN) -> None:
    """Stamp a dataset with a gain-profile tag."""
    write_gain_profile(root, profile)


def set_robot_type(root: Path, robot_type: str) -> None:
    """Overwrite the dataset's `robot_type` in `meta/info.json`.

    Real synthetic recordings carry `robot_type=None`; this forces a concrete value so
    a robot-type mismatch can be exercised.
    """
    path = root / INFO_RELATIVE_PATH
    info = json.loads(path.read_text(encoding="utf-8"))
    info[INFO_ROBOT_TYPE_KEY] = robot_type
    path.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")


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
