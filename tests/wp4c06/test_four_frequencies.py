"""CG-4C-06e — log_freq/save_freq/eval_steps/env_eval_freq are four distinct meanings.

`FR-TRN-040`: the four training frequencies must be exposed with four distinct
meanings, never collapsed into one "evaluation period", and `env_eval_freq` must be
marked unrelated to real OpenArm (it is a sim-rollout cadence).
"""

from __future__ import annotations

from backend.eval.selection import ENV_EVAL_FREQ_NOTE, FrequencyConfig
from backend.eval.selection.constants import (
    FREQ_ENV_EVAL,
    FREQ_EVAL_STEPS,
    FREQ_LOG,
    FREQ_SAVE,
)
from tests.wp4c06 import support

_FREQ = FrequencyConfig(log_freq=10, save_freq=1000, eval_steps=500, env_eval_freq=2000)


def test_four_names_are_distinct() -> None:
    """The four frequency names are four, not fewer (CG-4C-06e)."""
    rows, _ = _FREQ.meanings()
    names = [name for name, _value, _meaning in rows]
    assert names == [FREQ_LOG, FREQ_SAVE, FREQ_EVAL_STEPS, FREQ_ENV_EVAL]
    assert len(set(names)) == 4


def test_four_meanings_are_distinct() -> None:
    """No two frequencies share a meaning string — none is collapsed into another."""
    rows, _ = _FREQ.meanings()
    meanings = [meaning for _name, _value, meaning in rows]
    assert len(set(meanings)) == 4


def test_values_are_carried_per_frequency() -> None:
    """Each frequency carries its own value distinctly."""
    rows, _ = _FREQ.meanings()
    values = {name: value for name, value, _meaning in rows}
    assert values == {FREQ_LOG: 10, FREQ_SAVE: 1000, FREQ_EVAL_STEPS: 500, FREQ_ENV_EVAL: 2000}


def test_env_eval_freq_marked_unrelated_to_real_openarm() -> None:
    """`env_eval_freq` carries the distinct 'unrelated to real OpenArm' note."""
    _rows, note = _FREQ.meanings()
    assert note == ENV_EVAL_FREQ_NOTE
    assert "unrelated to real OpenArm" in note


def test_render_shows_all_four_with_env_note() -> None:
    """The scorecard render exposes all four frequencies and the env note."""
    text = support.scorecard(support.checkpoint(), 18, 20).render()
    for name in (FREQ_LOG, FREQ_SAVE, FREQ_EVAL_STEPS, FREQ_ENV_EVAL):
        assert name in text
    assert ENV_EVAL_FREQ_NOTE in text
