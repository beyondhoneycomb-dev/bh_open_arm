"""CG-5-05e — the report states the residual-risk line verbatim.

A passing load test does not erase the fact that the soft E-stop can be as late as
head-of-line blocking and the only device outside HOL is the physical power-line
button. The report must carry that statement verbatim.
"""

from __future__ import annotations

from backend.loadtest import LoadRun, build_load_test_report
from backend.loadtest.constants import RESIDUAL_RISK_STATEMENT


def test_report_carries_the_residual_risk_verbatim(saturated_run: LoadRun) -> None:
    report = build_load_test_report(saturated_run)
    assert report.artifact["cg_5_05e_residual_risk"] == RESIDUAL_RISK_STATEMENT


def test_residual_risk_names_the_physical_power_button() -> None:
    # The load-bearing phrase the acceptance requires, independent of surrounding prose.
    assert "the real safety device is the physical power-line button" in RESIDUAL_RISK_STATEMENT
    assert "head-of-line" in RESIDUAL_RISK_STATEMENT
