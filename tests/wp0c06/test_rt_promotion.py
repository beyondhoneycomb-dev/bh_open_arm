"""RT promotion reports the honest truth about what it could and could not do (⑤).

`chrt -f` + `mlockall` may or may not be permitted; either way the outcome is
published verbatim, and "applied" must reflect the real `os.sched_getscheduler`
readback, never an assumption. The promotion is exercised in a child process so a
successful SCHED_FIFO change (if the runner is privileged) cannot touch the test
runner — exactly how the harness isolates condition 6.
"""

from __future__ import annotations

import multiprocessing as mp
from typing import Any

import pytest

from sim.harness.rt_promotion import promote_realtime, restore_normal


def _promote_in_child(result_queue: Any) -> None:
    """Attempt RT promotion in an isolated child and return its record."""
    record = promote_realtime().as_record()
    restore_normal()
    result_queue.put(record)


def _run_promotion() -> dict[str, Any]:
    """Run the promotion attempt in a forked child and collect its record."""
    context = mp.get_context("fork")
    queue = context.Queue()
    process = context.Process(target=_promote_in_child, args=(queue,))
    process.start()
    record = queue.get()
    process.join(timeout=10.0)
    return record


def test_promotion_record_is_internally_consistent() -> None:
    """`applied` is exactly the conjunction of the scheduler and mlockall results."""
    record = _run_promotion()
    assert record["applied"] == (record["sched_applied"] and record["mlockall_applied"])
    assert isinstance(record["reason"], str) and record["reason"]
    # No-gain vs could-not-apply must be tellable apart: a refused promotion says so.
    if not record["applied"]:
        assert (
            "not attempted" in record["reason"]
            or "refused" in record["reason"]
            or "partial" in record["reason"]
        )


def test_promotion_reports_the_scheduler_readback() -> None:
    """The record names the before/after scheduler policy from the real readback."""
    record = _run_promotion()
    assert "policy_before" in record
    assert "policy_after" in record
    # applied implies the readback actually shows SCHED_FIFO — never assumed.
    if record["applied"]:
        assert record["policy_after"] == "SCHED_FIFO"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
