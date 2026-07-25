"""CG-4C-03f — the report is self-baseline and references no external baseline.

`FR-SIM-059`: no official OpenArm sim2real baseline exists, so every number is a
self-measured baseline and there is nowhere in the contract to record an external
one. This is enforced structurally: `baseline_kind` is fixed, and the report has no
field for an external/official/reference baseline.
"""

from __future__ import annotations

import dataclasses

from backend.eval.stats import SELF_BASELINE_KIND, SuccessRateReport
from backend.eval.stats.report import SuccessRateReportError
from tests.wp4c03.support import report

_FORBIDDEN_BASELINE_TOKENS = ("external", "official", "reference", "sim2real")


def test_report_baseline_kind_is_self_baseline() -> None:
    """CG-4C-03f: the produced report is stamped self-baseline."""
    assert report(n_success=10, n_trials=20).baseline_kind == SELF_BASELINE_KIND
    assert SELF_BASELINE_KIND == "self-baseline"


def test_render_stamps_self_baseline() -> None:
    """The rendered report carries the self-baseline token (CG-4C-03f)."""
    assert "self-baseline" in report(n_success=10, n_trials=20).render()


def test_non_self_baseline_is_refused() -> None:
    """A report claiming any other baseline kind is refused at validation."""
    rep = report(n_success=10, n_trials=20)
    forged = dataclasses.replace(rep, baseline_kind="official-openarm-2026")
    try:
        forged.validate()
    except SuccessRateReportError:
        return
    raise AssertionError("a non-self baseline_kind must be refused (FR-SIM-059)")


def test_no_external_baseline_field_in_contract() -> None:
    """Static: the report has no data slot for an external/official baseline.

    "외부 기준선 참조 0건" means there is nowhere to put one — the only baseline
    field is `baseline_kind`, and no field name names an external reference.
    """
    field_names = {field.name for field in dataclasses.fields(SuccessRateReport)}
    assert "baseline_kind" in field_names
    for name in field_names:
        for token in _FORBIDDEN_BASELINE_TOKENS:
            assert token not in name.lower(), f"field {name!r} references an external baseline"
