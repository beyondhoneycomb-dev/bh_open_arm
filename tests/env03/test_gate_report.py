"""WP-ENV-03 acceptance ⑤ ⑦ — CI auto-publishes only PASS/FAIL_BLOCKING; blocking blocks."""

from __future__ import annotations

import gate_report
import pytest


def test_job_result_maps_to_pass_or_fail_blocking_only() -> None:
    assert gate_report.map_job_result(True) == "PASS"
    assert gate_report.map_job_result(False) == "FAIL_BLOCKING"


def test_ci_may_not_auto_publish_retry_or_degraded() -> None:
    for state in ("RETRY_WITH_VARIANT", "DEGRADED_ACCEPTED"):
        with pytest.raises(gate_report.AutoPublishError):
            gate_report.assert_auto_publishable(state)


def test_pass_and_fail_blocking_are_auto_publishable() -> None:
    assert gate_report.assert_auto_publishable("PASS") == "PASS"
    assert gate_report.assert_auto_publishable("FAIL_BLOCKING") == "FAIL_BLOCKING"


def test_fail_blocking_gate_blocks_merge() -> None:
    decision = gate_report.merge_decision(
        {"pin-verify": "PASS", "contract-regress": "FAIL_BLOCKING"}
    )
    assert not decision.allowed
    assert decision.blocking == ("contract-regress",)


def test_all_pass_permits_merge() -> None:
    decision = gate_report.merge_decision({"pin-verify": "PASS", "lint": "PASS"})
    assert decision.allowed
