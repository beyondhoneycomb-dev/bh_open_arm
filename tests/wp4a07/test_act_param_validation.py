"""CG-4A-07c — ACT `temporal_ensemble_coeff` set with `n_action_steps != 1` is rejected.

The rejection carries a distinct reason and a message that names the offending value,
so the UI can say *why*. The companion `n_action_steps > chunk_size` rule is checked
here too, with its own distinct reason, to prove the two ACT constraints are never
merged into one verdict.
"""

from __future__ import annotations

import pytest

from backend.inference.adapter import (
    ActParams,
    InferenceParamError,
    InferenceParamReason,
    validate_act_params,
)


def test_temporal_ensemble_with_multistep_rejected_with_reason() -> None:
    """Ensembling on with `n_action_steps != 1` raises the ensemble reason and explains it."""
    with pytest.raises(InferenceParamError) as excinfo:
        validate_act_params(ActParams(temporal_ensemble_coeff=0.01, n_action_steps=100))
    assert excinfo.value.reason is InferenceParamReason.ACT_TEMPORAL_ENSEMBLE_ACTION_STEPS
    assert "n_action_steps" in str(excinfo.value)


def test_temporal_ensemble_with_single_step_is_allowed() -> None:
    """Ensembling on with `n_action_steps == 1` passes (the LeRobot-permitted shape)."""
    validate_act_params(ActParams(temporal_ensemble_coeff=0.01, n_action_steps=1))


def test_action_steps_exceeding_chunk_rejected_distinctly() -> None:
    """`n_action_steps > chunk_size` raises its own distinct reason, not the ensemble one."""
    with pytest.raises(InferenceParamError) as excinfo:
        validate_act_params(ActParams(n_action_steps=200, chunk_size=100))
    assert excinfo.value.reason is InferenceParamReason.ACT_ACTION_STEPS_EXCEED_CHUNK


def test_default_act_params_pass() -> None:
    """The frozen ACT defaults (chunk_size=100, n_action_steps=100, no ensemble) validate."""
    validate_act_params(ActParams())
