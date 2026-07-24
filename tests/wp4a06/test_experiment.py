"""CG-4A-06b — a twin job with any of FR-TRN-073 (a)-(d) mismatched is refused.

`02c` §1.6 ②: the paired-experiment generator must refuse to pair two arms that
disagree on a shared control, and the paired result must store the four controls
once so a mismatch is unrepresentable. The arms differ in exactly one thing — the
projection — and that difference produces a 48-dim FULL arm and a 16-dim POS_ONLY
arm whose action target is position-only in both.
"""

from __future__ import annotations

import dataclasses

import pytest

from backend.training.projection import (
    PairedExperimentError,
    ProjectionKind,
    generate_paired_experiment,
)
from tests.wp4a06.fixtures import (
    SHARED_CONTROL_FIELDS,
    arm_request,
    matched_arm_pair,
    observation_config,
)

# The distinct value a mismatch test substitutes into one control at a time.
_MISMATCH_VALUES = {
    "repo_id": "openarm/other_repo",
    "revision": "deadbeef",
    "seed": 99,
    "rollout_set_id": "other_suite_v2",
    "success_criterion_id": "other_criterion_v2",
}


def test_matched_pair_generates_and_shares_controls() -> None:
    """Matched arms pair; the FULL/POS_ONLY widths and shared controls are correct."""
    config = observation_config()
    arm_a, arm_b = matched_arm_pair()
    experiment = generate_paired_experiment(arm_a, arm_b, config)

    assert experiment.arm_a.label == "FULL_48"
    assert experiment.arm_b.label == "POS_ONLY_16"
    assert experiment.arm_a.observation_dim == config.state_dim
    assert experiment.arm_b.observation_dim == config.state_dim // 3
    # The projection changes observation width only — the action target is
    # position-only and identical across arms.
    assert experiment.arm_a.action_dim == experiment.arm_b.action_dim == config.action_dim
    # The four controls are stored once and both arms read them from the parent.
    assert experiment.repo_id == arm_a.repo_id
    assert experiment.seed == arm_a.seed
    assert experiment.rollout_set_id == arm_a.rollout_set_id
    assert experiment.success_criterion_id == arm_a.success_criterion_id


@pytest.mark.parametrize("field", SHARED_CONTROL_FIELDS)
def test_any_control_mismatch_is_refused(field: str) -> None:
    """Mutating any single control (a)-(d) on one arm refuses the pairing."""
    config = observation_config()
    arm_a = arm_request(ProjectionKind.FULL)
    arm_b = arm_request(ProjectionKind.POS_ONLY, **{field: _MISMATCH_VALUES[field]})
    with pytest.raises(PairedExperimentError, match=field):
        generate_paired_experiment(arm_a, arm_b, config)


def test_multiple_mismatches_are_all_named() -> None:
    """A pairing that differs on several controls names each one in the refusal."""
    config = observation_config()
    arm_a = arm_request(ProjectionKind.FULL)
    arm_b = arm_request(
        ProjectionKind.POS_ONLY, seed=_MISMATCH_VALUES["seed"], repo_id=_MISMATCH_VALUES["repo_id"]
    )
    with pytest.raises(PairedExperimentError) as raised:
        generate_paired_experiment(arm_a, arm_b, config)
    assert "seed" in str(raised.value)
    assert "repo_id" in str(raised.value)


def test_wrong_projection_pairing_is_refused() -> None:
    """Two arms with the same projection are not the {FULL, POS_ONLY} ablation."""
    config = observation_config()
    arm_a = arm_request(ProjectionKind.FULL)
    arm_b = arm_request(ProjectionKind.FULL)
    with pytest.raises(PairedExperimentError, match="POS_ONLY"):
        generate_paired_experiment(arm_a, arm_b, config)


def test_swapped_projection_order_is_refused() -> None:
    """arm_a must be FULL and arm_b POS_ONLY — the reversed order is refused."""
    config = observation_config()
    arm_a = arm_request(ProjectionKind.POS_ONLY)
    arm_b = arm_request(ProjectionKind.FULL)
    with pytest.raises(PairedExperimentError):
        generate_paired_experiment(arm_a, arm_b, config)


def test_paired_experiment_has_no_per_arm_control_slots() -> None:
    """The controls live on the experiment, not the arms — a mismatch is unrepresentable."""
    arm_field_names = {field.name for field in dataclasses.fields(matched_arm_pair()[0])}
    # ArmRequest carries the controls (it is what a human writes and can get wrong),
    # but the resolved ExperimentArm must not — otherwise two arms could disagree.
    config = observation_config()
    experiment = generate_paired_experiment(*matched_arm_pair(), config)
    resolved_arm_fields = {field.name for field in dataclasses.fields(experiment.arm_a)}
    for control in SHARED_CONTROL_FIELDS:
        assert control in arm_field_names
        assert control not in resolved_arm_fields
