"""Synthetic 48-dim LeRobot v3.0 dataset generator.

`09` FR-SIM-020's spirit is that a synthetic dataset must be the real schema, not
a schema-shaped stand-in: this generator writes an actual LeRobot v3.0 dataset
(via `LeRobotDataset.create`, `CODEBASE_VERSION == "v3.0"`), so anything that
loads a real recording loads this one identically. It carries no camera streams —
the deliverable is the state/action statistics path, not video — and it opens no
CAN device (SPINE §5): it runs anywhere, before any hardware exists.

The vector shapes are the ones `10` FR-TRN-074 fixes. With
`use_velocity_and_torque=True` the bimanual `observation.state` is 48-dim
(16 position + 16 velocity + 16 torque, interleaved per motor), while `action` is
always position-only — 16-dim bimanual — because a policy predicts positions, not
velocities or torques. The three channel groups are drawn at different scales so
that a per-group normalization statistic is visibly distinct from the
mixed-vector one the normalization module warns about.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from backend.learning.channel_groups import action_channels, state_channels
from backend.learning.provenance import build_provenance_manifest

# Per-unit sample scales (standard deviation of the synthetic draw). They are
# deliberately different so the channel groups have visibly different statistics:
# a degree channel swings far wider than a torque channel, and a normalization
# statistic that pools them would be dominated by the widest group. Values are
# kept inside plausible physical envelopes (joint torque limits are ±7..±40 Nm).
_UNIT_SAMPLE_SCALE: dict[str, float] = {
    "Deg": 30.0,
    "DegPerSec": 60.0,
    "Nm": 4.0,
}


@dataclass(frozen=True)
class SyntheticDatasetSpec:
    """Configuration for one synthetic dataset.

    Attributes:
        repo_id: LeRobot repository identifier for the dataset.
        bimanual: True for the 48/16-dim two-arm layout.
        use_velocity_and_torque: True keeps velocity and torque in the state,
            giving the 48-dim (bimanual) `observation.state`.
        fps: Frame rate stored in the dataset metadata.
        episodes: Number of episodes to write.
        frames_per_episode: Frames written per episode.
        task: The task string attached to every frame.
        seed: Seed for the deterministic synthetic draw.
    """

    repo_id: str = "synthetic/openarm_bimanual_48"
    bimanual: bool = True
    use_velocity_and_torque: bool = True
    fps: int = 30
    episodes: int = 2
    frames_per_episode: int = 8
    task: str = "synthetic-openarm"
    seed: int = 0


@dataclass(frozen=True)
class BuildResult:
    """The outcome of writing a synthetic dataset.

    Attributes:
        root: Directory the dataset was written to.
        repo_id: The dataset's repository identifier.
        state_dim: Length of the `observation.state` vector.
        action_dim: Length of the `action` vector.
        num_frames: Total frames written.
        num_episodes: Total episodes written.
        provenance: The provenance manifest carrying env and normalization hashes.
    """

    root: Path
    repo_id: str
    state_dim: int
    action_dim: int
    num_frames: int
    num_episodes: int
    provenance: dict[str, Any]


def state_action_feature_spec(spec: SyntheticDatasetSpec) -> dict[str, dict[str, Any]]:
    """Build the LeRobot features dict for a synthetic dataset.

    The `names` arrays carry the per-index channel names from the frozen unit
    contract, so the loaded dataset can be split back into unit groups without a
    second source of truth.

    Args:
        spec: The dataset configuration.

    Returns:
        (dict) A LeRobot features dict with `observation.state` and `action`.
    """
    obs = state_channels(
        bimanual=spec.bimanual, use_velocity_and_torque=spec.use_velocity_and_torque
    )
    act = action_channels(bimanual=spec.bimanual)
    return {
        "observation.state": {
            "dtype": "float32",
            "shape": (len(obs),),
            "names": [channel.name for channel in obs],
        },
        "action": {
            "dtype": "float32",
            "shape": (len(act),),
            "names": [channel.name for channel in act],
        },
    }


def generate_state_action_arrays(
    spec: SyntheticDatasetSpec,
) -> tuple[npt.NDArray[np.float32], npt.NDArray[np.float32]]:
    """Draw the synthetic state and action matrices deterministically.

    Each state column is drawn at its unit group's scale so the groups differ, and
    the action is a plausible position target drawn at the degree scale.

    Args:
        spec: The dataset configuration.

    Returns:
        (tuple[np.ndarray, np.ndarray]) The `(states, actions)` matrices, each of
        shape `(episodes * frames_per_episode, dim)` and dtype float32.
    """
    rng = np.random.default_rng(spec.seed)
    obs = state_channels(
        bimanual=spec.bimanual, use_velocity_and_torque=spec.use_velocity_and_torque
    )
    act = action_channels(bimanual=spec.bimanual)
    rows = spec.episodes * spec.frames_per_episode

    scales = np.array([_UNIT_SAMPLE_SCALE[channel.unit_name] for channel in obs], dtype=np.float64)
    states = rng.standard_normal((rows, len(obs))) * scales
    action_scale = _UNIT_SAMPLE_SCALE["Deg"]
    actions = rng.standard_normal((rows, len(act))) * action_scale
    return states.astype(np.float32), actions.astype(np.float32)


def _available_rgb_encoder() -> Any:
    """Return an RGB encoder config whose codec this platform can construct.

    LeRobot 0.6.0's `DatasetWriter` builds an RGB encoder even for a dataset with
    no video features, and its default codec (`libsvtav1`) is unavailable with the
    pyav backend on many platforms. Since no frame is ever encoded here, any
    constructible software codec serves; this picks the first one the platform
    reports, so the state-only dataset can be created without a real AV1 encoder.

    Returns:
        (RGBEncoderConfig | None) A constructible encoder config, or None to let
        LeRobot use its own default when detection turns up nothing.
    """
    from lerobot.configs.video import VALID_VIDEO_CODECS, RGBEncoderConfig
    from lerobot.datasets import detect_available_encoders_pyav

    available = detect_available_encoders_pyav(VALID_VIDEO_CODECS)
    for codec in sorted(available):
        try:
            return RGBEncoderConfig(vcodec=codec)
        except ValueError:
            continue
    return None


def build_synthetic_dataset(spec: SyntheticDatasetSpec, root: Path) -> BuildResult:
    """Write a synthetic LeRobot v3.0 dataset and its provenance manifest.

    Args:
        spec: The dataset configuration.
        root: Directory to write the dataset into.

    Returns:
        (BuildResult) Facts about the written dataset, including its provenance
        manifest with the env and normalization hashes.
    """
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    features = state_action_feature_spec(spec)
    states, actions = generate_state_action_arrays(spec)

    create_kwargs: dict[str, Any] = {"use_videos": False}
    rgb_encoder = _available_rgb_encoder()
    if rgb_encoder is not None:
        create_kwargs["rgb_encoder"] = rgb_encoder

    dataset = LeRobotDataset.create(
        repo_id=spec.repo_id,
        fps=spec.fps,
        features=features,
        root=root,
        **create_kwargs,
    )

    frame = 0
    for _ in range(spec.episodes):
        for _ in range(spec.frames_per_episode):
            dataset.add_frame(
                {
                    "observation.state": states[frame],
                    "action": actions[frame],
                    "task": spec.task,
                }
            )
            frame += 1
        dataset.save_episode()
    if hasattr(dataset, "finalize"):
        dataset.finalize()

    state_dim = int(features["observation.state"]["shape"][0])
    action_dim = int(features["action"]["shape"][0])
    provenance = build_provenance_manifest(
        {
            "repo_id": spec.repo_id,
            "root": str(root),
            "codebase_version": "v3.0",
            "state_dim": state_dim,
            "action_dim": action_dim,
            "use_velocity_and_torque": spec.use_velocity_and_torque,
            "bimanual": spec.bimanual,
            "num_frames": frame,
            "num_episodes": spec.episodes,
        }
    )

    return BuildResult(
        root=root,
        repo_id=spec.repo_id,
        state_dim=state_dim,
        action_dim=action_dim,
        num_frames=frame,
        num_episodes=spec.episodes,
        provenance=provenance,
    )
