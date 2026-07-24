"""WP-3D-06 ④ — physical split vs training eval_split, and the pre-training block.

`FR-DAT-048`/`049` / `02b` §8.2 WP-3D-06 ④: the physical `split` and the training
`dataset.eval_split` are different layers; their composition is computed for display, and
`eval_steps > 0` with `eval_split == 0.0` is blocked before training.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.dataset.merge.trainval import (
    EvalConfigError,
    compose_split_ratios,
    eval_split_of,
    validate_eval_config,
)


def test_eval_steps_without_holdout_blocked() -> None:
    """eval_steps > 0 with eval_split == 0.0 has nothing to evaluate on, so it is blocked."""
    with pytest.raises(EvalConfigError, match="FR-DAT-049"):
        validate_eval_config(eval_steps=1000, eval_split=0.0)


def test_eval_steps_with_holdout_allowed() -> None:
    """A positive eval_split gives eval_steps data to run on."""
    validate_eval_config(eval_steps=1000, eval_split=0.1)


def test_no_eval_steps_needs_no_holdout() -> None:
    """eval_steps == 0 does not require a holdout."""
    validate_eval_config(eval_steps=0, eval_split=0.0)


def test_eval_split_out_of_range_refused() -> None:
    """An eval_split outside [0, 1) is not a valid holdout fraction."""
    with pytest.raises(EvalConfigError, match="outside"):
        validate_eval_config(eval_steps=0, eval_split=1.0)


def test_composition_is_the_product() -> None:
    """A 0.8 physical train split with a 0.1 eval holdout trains on 0.72 and evals 0.08."""
    composed = compose_split_ratios(
        {"train": 0.8, "val": 0.2}, eval_split=0.1, trained_split="train"
    )
    assert composed.effective_train == pytest.approx(0.72)
    assert composed.effective_eval == pytest.approx(0.08)
    assert composed.untouched == {"val": 0.2}


def test_eval_split_of_reads_config_and_defaults() -> None:
    """A training config's dataset.eval_split is read, defaulting to 0.0 when absent."""
    with_split = SimpleNamespace(dataset=SimpleNamespace(eval_split=0.15))
    without = SimpleNamespace(dataset=SimpleNamespace())
    assert eval_split_of(with_split) == pytest.approx(0.15)
    assert eval_split_of(without) == 0.0
    assert eval_split_of(SimpleNamespace()) == 0.0
