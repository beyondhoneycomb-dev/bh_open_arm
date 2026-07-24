"""CG-4A-03d (runtime) — no clearance while a degeneracy is undecided (`FR-TRN-068`).

The static half of CG-4A-03d is `test_no_bypass.py`; this half proves the gate's
runtime behaviour: it raises on an undecided finding and on a dataset that has not
passed preflight, and mints a clearance only when every finding is resolved.
"""

from __future__ import annotations

import pytest

from backend.training.degenerate import (
    DegenerateChoice,
    DegenerateDecision,
    DegenerateFinding,
    DegenerateGateError,
    NormMode,
    TrainingClearance,
    clear_for_training,
    present_choices,
    undecided_findings,
)
from backend.training.preflight import (
    Component,
    PreflightCode,
    PreflightFinding,
    PreflightReport,
)


def _finding() -> DegenerateFinding:
    return DegenerateFinding(
        channel_name="left_joint_2.vel",
        joint="left_joint_2",
        component=Component.VEL,
        norm_mode=NormMode.MEAN_STD,
        statistic=0.0,
        threshold=1e-4,
        amplification_estimate=1e8,
    )


def _passed() -> PreflightReport:
    return PreflightReport.from_findings(())


def _blocked() -> PreflightReport:
    return PreflightReport.from_findings(
        (
            PreflightFinding(
                code=PreflightCode.OBSERVATION_STATE_ORDER,
                channel_name="observation.state",
                component=None,
                joint=None,
                detail="rotated",
            ),
        )
    )


def test_present_choices_offers_exactly_the_three() -> None:
    choices = present_choices()
    assert set(choices) == set(DegenerateChoice)
    assert len(choices) == 3


def test_undecided_finding_blocks_clearance() -> None:
    finding = _finding()
    with pytest.raises(DegenerateGateError):
        clear_for_training(_passed(), (finding,), ())


def test_decided_finding_mints_a_clearance() -> None:
    finding = _finding()
    decision = DegenerateDecision(finding, DegenerateChoice.EXCLUDE, "stationary joint, drop it")
    clearance = clear_for_training(_passed(), (finding,), (decision,))
    assert isinstance(clearance, TrainingClearance)
    assert clearance.decisions == (decision,)


def test_clean_dataset_clears_with_no_findings() -> None:
    clearance = clear_for_training(_passed(), (), ())
    assert clearance.reviewed_findings == ()


def test_a_dataset_that_failed_preflight_cannot_be_cleared() -> None:
    with pytest.raises(DegenerateGateError):
        clear_for_training(_blocked(), (), ())


def test_partially_decided_findings_still_block() -> None:
    decided = _finding()
    other = DegenerateFinding(
        channel_name="right_gripper.torque",
        joint="right_gripper",
        component=Component.TORQUE,
        norm_mode=NormMode.MEAN_STD,
        statistic=0.0,
        threshold=1e-4,
        amplification_estimate=1e8,
    )
    decision = DegenerateDecision(decided, DegenerateChoice.PROCEED, "accepted knowingly")
    pending = undecided_findings((decided, other), (decision,))
    assert pending == (other,)
    with pytest.raises(DegenerateGateError):
        clear_for_training(_passed(), (decided, other), (decision,))
