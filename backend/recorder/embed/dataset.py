"""In-process `LeRobotDataset` construction for the recorder embed (WP-3B-11).

The embed builds the dataset by calling `LeRobotDataset.create()` directly, in
this process — never by spawning the `lerobot record` console script, which would
reconnect the robot on every invocation and destroy its zero calibration (`02b`
§6.2 WP-3B-11). This module is that construction and the three guards LeRobot's
own CLI applies before it: the `eval_`-name refusal (acceptance ⑥), the `repo_id`
stamp that makes each session's name unique and is what display, save and later
reference all use (acceptance ⑤), and the video-codec workaround this host needs.

The `action`/`observation.state` feature bodies are derived from `CTR-REC@v1`, and
the produced `meta/info.json` is validated back against the contract so an
out-of-contract key or a poisoned `action` cannot leave this function unnoticed.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from lerobot.configs.video import VALID_VIDEO_CODECS, RGBEncoderConfig
from lerobot.datasets import detect_available_encoders_pyav
from lerobot.datasets.lerobot_dataset import LeRobotDataset

from backend.recorder.embed.constants import (
    EVAL_NAME_PREFIX,
    REPO_ID_SEPARATOR,
    REPO_ID_STAMP_FORMAT,
    REPO_ID_STAMP_JOINER,
)
from contracts.recorder import (
    ACTION_KEY,
    OBSERVATION_STATE_KEY,
    RecorderConfig,
    RecorderContractError,
    action_dim,
    action_names,
    observation_state_names,
    validate_info_features,
)

# `LeRobotDataset.create` writes `observation.state`/`action` as a 1-D float32
# vector; the shape is the channel count and the names are the per-channel labels.
_FLOAT32 = "float32"


class RecorderNameError(ValueError):
    """Raised when a `repo_id` names an `eval_` dataset the recorder must refuse.

    An `eval_` dataset is produced by policy evaluation (`lerobot-rollout`), never
    by data collection, so recording under that name is the reserved-prefix defect
    (WP-3B-11 acceptance ⑥).
    """


def reject_eval_name(repo_id: str) -> None:
    """Refuse a `repo_id` whose dataset-name half is reserved for evaluation.

    Args:
        repo_id: The requested repository id, `account/name` or bare `name`.

    Raises:
        RecorderNameError: When the dataset-name half starts with `eval_`.
    """
    dataset_name = repo_id.rsplit(REPO_ID_SEPARATOR, 1)[-1]
    if dataset_name.startswith(EVAL_NAME_PREFIX):
        raise RecorderNameError(
            f"dataset name {dataset_name!r} starts with the reserved {EVAL_NAME_PREFIX!r} prefix; "
            "eval_ names are for policy evaluation (lerobot-rollout), not data collection"
        )


def stamp_repo_id(repo_id: str, moment: datetime | None = None) -> str:
    """Append a date-time tag so each recording session gets a unique `repo_id`.

    Mirrors `DatasetRecordConfig.stamp_repo_id`, replicated because that config
    cannot be constructed on a host whose default video codec is unavailable — its
    `__post_init__` builds an encoder eagerly and raises. The stamped name is the
    one carried through display, storage and reference (WP-3B-11 acceptance ⑤).

    Args:
        repo_id: The base repository id.
        moment: The timestamp to stamp; defaults to now.

    Returns:
        (str) The stamped id, or the input unchanged when it is empty.
    """
    if not repo_id:
        return repo_id
    stamp = (moment or datetime.now()).strftime(REPO_ID_STAMP_FORMAT)
    return f"{repo_id}{REPO_ID_STAMP_JOINER}{stamp}"


def resolve_rgb_encoder() -> RGBEncoderConfig | None:
    """Return an RGB encoder config whose codec this host can actually construct.

    LeRobot 0.6.0 builds an RGB encoder inside `DatasetWriter` even for a dataset
    with no video features, and its default codec (`libsvtav1`) is unavailable with
    the pyav backend on this host. No frame is ever encoded by a state/action
    recording, so any constructible software codec serves; this picks the first the
    platform reports, or None to let LeRobot try its own default when none is found.

    Returns:
        (RGBEncoderConfig | None) A constructible encoder config, or None.
    """
    for codec in sorted(detect_available_encoders_pyav(VALID_VIDEO_CODECS)):
        try:
            return RGBEncoderConfig(vcodec=codec)
        except ValueError:
            continue
    return None


def create_features(config: RecorderConfig) -> dict[str, dict[str, Any]]:
    """Build the `LeRobotDataset.create` feature map for a `CTR-REC@v1` config.

    Only `action` and `observation.state` are declared here; LeRobot merges the
    five default meta features itself, and the closed key set is checked on the
    produced `info.json`. The `action` names are the position-only set, independent
    of `use_velocity_and_torque`.

    Args:
        config: The recorder configuration.

    Returns:
        (dict) The feature map for `action` and `observation.state`.
    """
    state_channels = observation_state_names(config.bimanual, config.use_velocity_and_torque)
    return {
        ACTION_KEY: {
            "dtype": _FLOAT32,
            "shape": (action_dim(config.bimanual),),
            "names": list(action_names(config.bimanual)),
        },
        OBSERVATION_STATE_KEY: {
            "dtype": _FLOAT32,
            "shape": (len(state_channels),),
            "names": list(state_channels),
        },
    }


def create_record_dataset(
    repo_id: str,
    fps: int,
    config: RecorderConfig,
    root: Path,
    moment: datetime | None = None,
) -> tuple[Any, str]:
    """Create the recording dataset in-process and return it with its stamped name.

    Refuses an `eval_` name, stamps the `repo_id`, builds the `CTR-REC@v1` feature
    bodies, creates a real `LeRobotDataset` (no CLI spawn), and validates the
    produced `meta/info.json` back against the contract so an out-of-contract key or
    a poisoned `action` is caught at creation rather than after a session's data is
    written.

    Args:
        repo_id: The requested repository id.
        fps: The recording frame rate, stored in the dataset metadata.
        config: The recorder configuration the feature set is derived from.
        root: The directory the dataset is written under.
        moment: The stamp timestamp; defaults to now.

    Returns:
        (tuple[LeRobotDataset, str]) The write-mode dataset and its stamped `repo_id`.

    Raises:
        RecorderNameError: When the name is reserved for evaluation.
        RecorderContractError: When the produced info.json violates `CTR-REC@v1`.
    """
    reject_eval_name(repo_id)
    stamped_repo_id = stamp_repo_id(repo_id, moment)
    dataset = LeRobotDataset.create(
        repo_id=stamped_repo_id,
        fps=fps,
        features=create_features(config),
        root=root,
        use_videos=False,
        rgb_encoder=resolve_rgb_encoder(),
    )
    _validate_produced_dataset(dataset, config)
    return dataset, stamped_repo_id


def _validate_produced_dataset(dataset: Any, config: RecorderConfig) -> None:
    """Validate a freshly created dataset's `info.json` features against `CTR-REC@v1`.

    Args:
        dataset: The created `LeRobotDataset`.
        config: The configuration it was created under.

    Raises:
        RecorderContractError: On any out-of-contract key or a non-position `action`.
    """
    features = dataset.meta.info.features
    try:
        validate_info_features(features, config)
    except RecorderContractError:
        # Never leave a half-open writer behind on the defect path.
        dataset.finalize()
        raise
