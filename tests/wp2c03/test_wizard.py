"""The wizard's canon rule, provenance and effective-threshold display (WP-2C-03).

`12` FR-SAF-060 makes the calibration output the threshold canon, and only after a real
collision-free run under an operator's no-collision judgment. These tests hold the line THE
ONE RULE draws: a synthetic proposal is never canon and `require_canonical` refuses it, an
attested real proposal is canon, and an unattested one is recorded but not adopted. They also
hold that the display shows the `12` FR-SAF-020 literature default and its "NOT measured"
label beside the calibrated value, sourced from WP-1-06 so the label has one definition.
"""

from __future__ import annotations

import pytest

from backend.safety_bringup.constants import ARM_JOINT_COUNT
from backend.safety_bringup.thresholds import default_collision_thresholds
from backend.threshold_calib import (
    PROVENANCE_SYNTHETIC,
    CalibrationNotCanonicalError,
    NoCollisionJudgment,
    ResidualStats,
    ThresholdProposal,
    attested_calibration,
    effective_threshold_display,
    propose_max_plus_sigma,
    synthetic_calibration,
)


def _proposal() -> ThresholdProposal:
    stats = tuple(ResidualStats(index, 1.0, 0.1, 0.0, 1000) for index in range(ARM_JOINT_COUNT))
    return propose_max_plus_sigma(stats)


def test_synthetic_calibration_is_not_canonical() -> None:
    calibration = synthetic_calibration(_proposal())
    assert not calibration.canonical
    assert calibration.provenance == PROVENANCE_SYNTHETIC
    assert calibration.judgment is None


def test_require_canonical_refuses_synthetic() -> None:
    # THE ONE RULE: an offline synthetic proposal cannot be presented as a measured threshold.
    calibration = synthetic_calibration(_proposal())
    with pytest.raises(CalibrationNotCanonicalError, match="not canonical"):
        calibration.require_canonical()


def test_attested_real_run_is_canonical() -> None:
    judgment = NoCollisionJudgment("operator-1", "sweep-A", attested=True, note="clean")
    calibration = attested_calibration(_proposal(), judgment)
    assert calibration.canonical
    thresholds = calibration.require_canonical()
    assert len(thresholds) == ARM_JOINT_COUNT


def test_unattested_real_run_is_recorded_but_not_canonical() -> None:
    # The operator saw a contact; the run is recorded, but its thresholds are not adopted.
    judgment = NoCollisionJudgment("operator-1", "sweep-B", attested=False, note="brushed cell")
    calibration = attested_calibration(_proposal(), judgment)
    assert not calibration.canonical
    assert calibration.judgment is not None
    with pytest.raises(CalibrationNotCanonicalError):
        calibration.require_canonical()


def test_display_shows_default_and_measured_label() -> None:
    calibration = synthetic_calibration(_proposal())
    display = effective_threshold_display(calibration)
    default = default_collision_thresholds()

    # The label is WP-1-06's, not a local copy — one definition of "NOT measured".
    assert display.default_label == default.label
    assert "NOT an OpenArm-measured value" in display.default_label
    assert not display.canonical
    assert len(display.rows) == ARM_JOINT_COUNT
    for row in display.rows:
        assert row.default_nm == pytest.approx(default.thresholds_nm[row.joint_index])
        assert row.calibrated_nm == pytest.approx(
            calibration.proposal.per_joint[row.joint_index].effective_nm
        )


def test_display_reports_floor_clamp_flags() -> None:
    # A wrist joint whose collision-free residual sits below the floor shows the clamp flag.
    stats = tuple(ResidualStats(index, 0.005, 0.001, 0.0, 1000) for index in range(ARM_JOINT_COUNT))
    calibration = synthetic_calibration(propose_max_plus_sigma(stats))
    display = effective_threshold_display(calibration)
    for row in display.rows:
        assert row.floor_clamped
        assert row.calibrated_nm == pytest.approx(row.floor_nm)
