"""CG-4C-05b — the report shows both conditions and the gap as a DERIVED value, no gap CI.

`02c` §3.5 ②: the report separates the two conditions and computes the generalization
gap as a derived scalar (`nominal - perturbed`). It must NOT assert a separate
confidence interval on the gap — a difference-of-two-binomials CI is a statistic the
spec grounds nowhere. This is enforced both behaviourally (the gap is a plain float)
and structurally (no field or type in the report attaches an interval to the gap).
"""

from __future__ import annotations

import dataclasses

from backend.eval.protocol import (
    Condition,
    DualConditionReport,
    DualConditionSet,
)
from backend.eval.protocol.constants import GAP_DERIVED_NO_CI_NOTE
from backend.eval.stats import ConfidenceInterval
from tests.wp4c05.support import arm, defined_protocol

_GAP_NAME_TOKENS = ("gap", "generalization")
_CI_NAME_TOKENS = ("ci", "interval", "confidence", "wilson", "clopper")


def _measured_report() -> DualConditionReport:
    """A report over a matched pair, so the gap is measured."""
    nominal = arm(Condition.NOMINAL, 16, 20, seed_base=0)
    perturbed = arm(Condition.PERTURBED, 10, 20, seed_base=100)
    dual = DualConditionSet.create(nominal, perturbed, defined_protocol())
    return DualConditionReport.of(dual)


def test_gap_is_derived_scalar() -> None:
    """The gap equals nominal - perturbed exactly, as a plain float (CG-4C-05b)."""
    report = _measured_report()
    assert report.gap_measured is True
    assert report.generalization_gap is not None
    expected = report.nominal.point_estimate - report.perturbed.point_estimate
    assert report.generalization_gap == expected
    assert isinstance(report.generalization_gap, float)


def test_both_conditions_render_separately() -> None:
    """The rendered report carries a distinct NOMINAL and PERTURBED section (CG-4C-05b)."""
    rendered = _measured_report().render()
    assert "NOMINAL" in rendered
    assert "PERTURBED" in rendered
    assert "일반화 격차(파생)" in rendered
    assert GAP_DERIVED_NO_CI_NOTE in rendered


def test_report_has_no_gap_confidence_interval_field() -> None:
    """Static: no report field attaches a confidence interval to the gap (CG-4C-05b ②).

    A field that names the gap and an interval in the same identifier, or a gap-named
    field typed as a `ConfidenceInterval`, would be the forbidden difference-CI. The
    gap field itself must be a plain scalar.
    """
    fields = dataclasses.fields(DualConditionReport)
    for field in fields:
        lowered = field.name.lower()
        names_gap = any(token in lowered for token in _GAP_NAME_TOKENS)
        names_ci = any(token in lowered for token in _CI_NAME_TOKENS)
        assert not (names_gap and names_ci), f"field {field.name!r} attaches a CI to the gap"
        if names_gap:
            assert "ConfidenceInterval" not in str(field.type), (
                f"gap field {field.name!r} is typed as a confidence interval"
            )

    gap_field = next(f for f in fields if f.name == "generalization_gap")
    assert "float" in str(gap_field.type), "the gap must be a plain scalar, not an interval"


def test_confidence_interval_import_is_only_for_arms_not_the_gap() -> None:
    """The per-arm Wilson CI exists, but the gap itself is a scalar difference.

    The conditions keep their own Wilson intervals (each arm's `SuccessRateReport`),
    which is correct; what is forbidden is a CI on their difference. This asserts the
    arms carry intervals while the gap does not.
    """
    report = _measured_report()
    assert isinstance(report.nominal.report.ci_wilson_95, ConfidenceInterval)
    assert isinstance(report.perturbed.report.ci_wilson_95, ConfidenceInterval)
    assert not isinstance(report.generalization_gap, ConfidenceInterval)
