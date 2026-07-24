"""The two split layers: a physical `split` vs a training `eval_split` (WP-3D-06).

`FR-DAT-048`/`049` and `02b` §8.2 WP-3D-06 ④: `lerobot-edit-dataset`'s `split` and a
training run's `dataset.eval_split` are *different layers*. The first physically
partitions the dataset on disk into whole-episode subsets (`split.py`); the second is a
training-time per-task holdout fraction (default `0.0`) carved from whatever split the
run trains on. They compose, and the composition is what an operator actually trains and
evaluates on, so it is computed and exposed here rather than left implicit.

The one hard block (`FR-DAT-049`, mirroring `TrainPipelineConfig.validate()`): a run that
asks for evaluation steps (`eval_steps > 0`) while holding out nothing
(`eval_split == 0.0`) has no data to evaluate on, and is refused before training starts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.dataset.merge.constants import DEFAULT_EVAL_SPLIT


class EvalConfigError(ValueError):
    """Raised when an evaluation configuration cannot produce an evaluation.

    The blocking case (`FR-DAT-049`): `eval_steps > 0` with `eval_split == 0.0` asks to
    evaluate with no held-out data. Also covers an `eval_split` outside `[0, 1)`.
    """


@dataclass(frozen=True)
class EffectiveSplitRatios:
    """The final proportions a physical split and an eval holdout compose to.

    `FR-DAT-048` requires the combined ratio to be shown when both layers apply. For a
    physical split fraction `p` of the dataset trained on, an `eval_split` of `e` carves
    `p * e` of the dataset into the training holdout and leaves `p * (1 - e)` for
    training; the other physical splits are untouched by the training holdout.

    Attributes:
        physical: The physical split fractions on disk (name to fraction).
        eval_split: The training-time per-task holdout fraction.
        trained_split: The physical split name the eval holdout is carved from.
        effective_train: The fraction of the whole dataset actually trained on.
        effective_eval: The fraction carved into the training holdout.
        untouched: The remaining physical splits and their fractions, unaffected by
            the eval holdout.
    """

    physical: dict[str, float]
    eval_split: float
    trained_split: str
    effective_train: float
    effective_eval: float
    untouched: dict[str, float]


def validate_eval_config(eval_steps: int, eval_split: float) -> None:
    """Refuse an evaluation asked for with no data to evaluate on.

    Args:
        eval_steps: The number of evaluation steps the training run requests.
        eval_split: The per-task holdout fraction the run reserves for evaluation.

    Raises:
        EvalConfigError: When `eval_split` is outside `[0, 1)`, or when `eval_steps > 0`
            while `eval_split == 0.0` (`FR-DAT-049`).
    """
    if not 0.0 <= eval_split < 1.0:
        raise EvalConfigError(
            f"eval_split {eval_split} is outside [0, 1); it is a per-task holdout fraction"
        )
    if eval_steps > 0 and eval_split == DEFAULT_EVAL_SPLIT:
        raise EvalConfigError(
            f"eval_steps={eval_steps} requests evaluation but eval_split={eval_split} holds "
            "out no data; set a positive eval_split or eval_steps=0 (WP-3D-06 blocked "
            "before training, FR-DAT-049)"
        )


def compose_split_ratios(
    physical: dict[str, float], eval_split: float, trained_split: str
) -> EffectiveSplitRatios:
    """Compute the final train/eval proportions a physical split and eval holdout make.

    Args:
        physical: The physical split fractions on disk; `trained_split` must be a key,
            and the fractions should sum to one.
        eval_split: The per-task holdout fraction (default `0.0`).
        trained_split: The physical split the training run trains on, from which the
            eval holdout is carved.

    Returns:
        (EffectiveSplitRatios) The composed proportions, for display (`FR-DAT-048`).

    Raises:
        EvalConfigError: When `eval_split` is outside `[0, 1)`.
        KeyError: When `trained_split` is not one of the physical splits.
    """
    if not 0.0 <= eval_split < 1.0:
        raise EvalConfigError(
            f"eval_split {eval_split} is outside [0, 1); it is a per-task holdout fraction"
        )
    trained_fraction = physical[trained_split]
    return EffectiveSplitRatios(
        physical=dict(physical),
        eval_split=eval_split,
        trained_split=trained_split,
        effective_train=trained_fraction * (1.0 - eval_split),
        effective_eval=trained_fraction * eval_split,
        untouched={name: fraction for name, fraction in physical.items() if name != trained_split},
    )


def eval_split_of(train_config: Any) -> float:
    """Read a training config's `dataset.eval_split`, defaulting to `0.0`.

    LeRobot's `DatasetConfig.eval_split` defaults to `0.0`; a config that omits it is
    read as that default rather than as an error, so the distinction stays honest even
    for a config that never mentions the field.

    Args:
        train_config: An object exposing a `dataset.eval_split` attribute, or one that
            omits it.

    Returns:
        (float) The configured eval split, or `0.0` when absent.
    """
    dataset = getattr(train_config, "dataset", None)
    if dataset is None:
        return DEFAULT_EVAL_SPLIT
    return float(getattr(dataset, "eval_split", DEFAULT_EVAL_SPLIT))
