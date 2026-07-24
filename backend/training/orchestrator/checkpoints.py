"""Locate and read LeRobot checkpoints from disk, without importing LeRobot.

The orchestrator launches `lerobot-train` as a subprocess on purpose (`02c` §1.1
대가: an in-process OOM would take the CAN-owning backend down with it), so it must
NOT import LeRobot in-process. It still has to find the checkpoints the trainer
writes — to preserve the last one on cancel (FR-TRN-032) and to build the
`--config_path` for a resume (FR-TRN-033). This module is that reader: the on-disk
layout is a stable contract of the trainer, so reading its files is not forking
its code.

The layout mirrors `lerobot.utils.constants` / `lerobot.common.train_utils` at
LeRobot 0.6.0: `<output_dir>/checkpoints/<step>/` holds `pretrained_model/` and
`training_state/training_step.json`, and `checkpoints/last` is a symlink to the
newest step directory. `get_step_identifier` zero-pads the step to at least six
digits, which is why the numeric sort is on the parsed int, not the name.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

# Mirror of lerobot.utils.constants (LeRobot 0.6.0). Kept as our own copy because
# importing lerobot in-process is exactly what the subprocess design forbids.
CHECKPOINTS_DIR = "checkpoints"
LAST_CHECKPOINT_LINK = "last"
PRETRAINED_MODEL_DIR = "pretrained_model"
TRAINING_STATE_DIR = "training_state"
TRAINING_STEP_FILE = "training_step.json"
TRAIN_CONFIG_NAME = "train_config.json"

_MIN_STEP_DIGITS = 6


@dataclass(frozen=True)
class Checkpoint:
    """One checkpoint directory on disk.

    Attributes:
        path: The step directory, `<output_dir>/checkpoints/<step>`.
        step: The training step it records.
    """

    path: Path
    step: int

    @property
    def train_config_path(self) -> Path:
        """The `train_config.json` a resume passes to `--config_path`.

        Returns:
            (Path) `<step>/pretrained_model/train_config.json`.
        """
        return self.path / PRETRAINED_MODEL_DIR / TRAIN_CONFIG_NAME

    @property
    def pretrained_model_dir(self) -> Path:
        """The saved-model directory inside this checkpoint."""
        return self.path / PRETRAINED_MODEL_DIR


def checkpoints_root(output_dir: Path) -> Path:
    """Return the checkpoints directory under a run output directory."""
    return output_dir / CHECKPOINTS_DIR


def read_step(checkpoint_dir: Path) -> int:
    """Read the training step a checkpoint records.

    Args:
        checkpoint_dir: A `<output_dir>/checkpoints/<step>` directory.

    Returns:
        (int) The step from `training_state/training_step.json`.

    Raises:
        FileNotFoundError: When the training-step file is absent.
        KeyError: When the file has no "step" key.
    """
    step_file = checkpoint_dir / TRAINING_STATE_DIR / TRAINING_STEP_FILE
    data = json.loads(step_file.read_text(encoding="utf-8"))
    return int(data["step"])


def _step_dirs(output_dir: Path) -> list[Path]:
    """List the numeric step directories under a run's checkpoints root."""
    root = checkpoints_root(output_dir)
    if not root.is_dir():
        return []
    return [child for child in root.iterdir() if child.is_dir() and child.name.isdigit()]


def find_last(output_dir: Path) -> Checkpoint | None:
    """Return the newest checkpoint of a run, or None when there is none.

    The `checkpoints/last` symlink is preferred because it is what LeRobot updates
    atomically on each save; the highest numeric step directory is the fallback for
    a tree whose symlink was not created (or does not survive the filesystem).

    Args:
        output_dir: The run output directory.

    Returns:
        (Checkpoint | None) The newest checkpoint, or None when absent.
    """
    root = checkpoints_root(output_dir)
    link = root / LAST_CHECKPOINT_LINK
    if link.is_dir():
        resolved = link.resolve()
        return Checkpoint(path=resolved, step=read_step(resolved))

    step_dirs = _step_dirs(output_dir)
    if not step_dirs:
        return None
    newest = max(step_dirs, key=lambda path: int(path.name))
    return Checkpoint(path=newest, step=read_step(newest))


def step_identifier(step: int, total_steps: int) -> str:
    """Format a step the way LeRobot names its checkpoint directories.

    Args:
        step: The step to format.
        total_steps: The run's total steps, which widens the field when large.

    Returns:
        (str) The zero-padded step directory name.
    """
    digits = max(_MIN_STEP_DIGITS, len(str(total_steps)))
    return f"{step:0{digits}d}"
