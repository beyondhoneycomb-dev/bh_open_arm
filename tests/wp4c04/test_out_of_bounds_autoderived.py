"""CG-4C-04b — POLICY_OUT_OF_BOUNDS is auto-derived from the dual log, never human-assigned."""

from __future__ import annotations

from backend.eval.taxonomy import (
    CorrelationEngine,
    FailureTag,
    TagDerivation,
    placeholder_taxonomy_thresholds,
    spec_for,
)
from tests.wp4c04.support import (
    clean_record,
    joint_limit_clamp_record,
    nan_reject_record,
    signals,
)


def _engine() -> CorrelationEngine:
    return CorrelationEngine(placeholder_taxonomy_thresholds())


def test_clamp_in_dual_log_yields_out_of_bounds() -> None:
    """A genuine joint-limit clamp in the dual log is auto-derived to POLICY_OUT_OF_BOUNDS."""
    tags = _engine().correlate(signals(dual_records=(joint_limit_clamp_record(),)))
    assert FailureTag.POLICY_OUT_OF_BOUNDS in tags


def test_out_of_bounds_cannot_exist_without_the_dual_record() -> None:
    """With no dual records the tag cannot appear — it has no other source (FR-INF-047)."""
    tags = _engine().correlate(signals(dual_records=()))
    assert FailureTag.POLICY_OUT_OF_BOUNDS not in tags


def test_nan_reject_is_not_out_of_bounds() -> None:
    """A NaN-reject record has clamp_detected True but reason NONE — it is INVALID_OUTPUT.

    This is the discriminator: keying only on requested != accepted would mis-tag a
    reject; keying on the JOINT_LIMIT clamp reason keeps the two apart.
    """
    tags = _engine().correlate(signals(dual_records=(nan_reject_record(),), nan_inf_rejections=1))
    assert FailureTag.POLICY_OUT_OF_BOUNDS not in tags
    assert FailureTag.POLICY_INVALID_OUTPUT in tags


def test_clean_record_yields_no_out_of_bounds() -> None:
    """An in-range record clamps nothing, so no out-of-bounds tag."""
    tags = _engine().correlate(signals(dual_records=(clean_record(),)))
    assert FailureTag.POLICY_OUT_OF_BOUNDS not in tags


def test_out_of_bounds_is_machine_derived_not_human() -> None:
    """The tag's derivation is AUTO — it is never a human-assigned field (CG-4C-04b)."""
    assert spec_for(FailureTag.POLICY_OUT_OF_BOUNDS).derivation is TagDerivation.AUTO
