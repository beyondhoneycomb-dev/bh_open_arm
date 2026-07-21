"""Acceptance ⑥ — the harness fixes no numeric threshold and renders no verdict.

This WP produces the distribution and the harness; PG-IK-001 sets the pass/fail
number after measurement. The CLI must exit 0 and emit descriptive statistics with
no verdict field.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("mujoco")
pytest.importorskip("mink")
pytest.importorskip("lerobot")

from sim.fkik import roundtrip

_VERDICT_KEYS = {"pass", "passed", "fail", "failed", "verdict", "threshold", "ok"}


def test_cli_exits_zero_and_renders_no_verdict(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = roundtrip.main(["--samples", "8", "--seed", "0"])
    assert exit_code == 0
    record = json.loads(capsys.readouterr().out)
    # A distribution is emitted, but nothing that reads as a pass/fail decision.
    assert "residual_percentiles_m" in record
    assert _VERDICT_KEYS.isdisjoint(record.keys())


def test_report_carries_statistics_not_a_threshold() -> None:
    report = roundtrip.run_distribution(samples=8, seed=0)
    record = report.to_dict()
    assert set(record["residual_percentiles_m"]) == {
        "p50",
        "p90",
        "p95",
        "p99",
        "min",
        "max",
        "mean",
    }
    assert _VERDICT_KEYS.isdisjoint(record.keys())
