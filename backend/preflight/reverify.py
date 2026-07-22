"""Re-verification hook for the deferred item: the *live* RID cross-check (plan 02a §4.1).

Four of the five preconditions run in full on this host — side, CAN-FD link, writer
lock, and clamp-canon need no motors. The fifth, the RID 21/22/23 cross-check, runs its
*gate logic* here on synthetic reads, but its *live* form needs sixteen powered motors
with torque OFF asserted first (`12` FR-SAF-075), which this host cannot supply. That
live read is deferred — SKIPPED WITH A REASON in the bound test, never asserted green —
and wired to this hook, which re-runs the identical torque gate against real captured
bytes the moment a capture directory is supplied via `OPENARM_RID_REAL_FIXTURE`.

The read and judgment are reused wholesale from `backend.can.rid.reverify`
(`WP-0B-07`); this module only re-applies the WP-2A-09 torque gate to each real
evaluation, so the deferred acceptance re-runs the exact code the offline gate tests
exercise, now pointed at real motors.
"""

from __future__ import annotations

from pathlib import Path

from backend.can.rid.reverify import (
    DEFAULT_MARGIN_LSB,
    FIXTURE_ENV_VAR,
    fixture_dir_from_env,
    reverify_from_fixture,
)
from backend.preflight.checks import check_rid_crosscheck
from backend.preflight.model import CheckResult, RidCrosscheck

__all__ = [
    "DEFAULT_MARGIN_LSB",
    "FIXTURE_ENV_VAR",
    "fixture_dir_from_env",
    "reverify_rid_crosscheck",
]


def reverify_rid_crosscheck(
    fixture_dir: Path, margin_lsb: int = DEFAULT_MARGIN_LSB
) -> list[CheckResult]:
    """Re-run the RID torque gate against real captured dumps, one per interface.

    Loads and judges every capture through `backend.can.rid.reverify.reverify_from_fixture`
    — the same decode, RID 9, RID 21/22/23 and J7 judgments the offline path uses — then
    applies `check_rid_crosscheck` to each. This is the re-verification the deferred live
    RID cross-check requires.

    Args:
        fixture_dir: Directory of captured RID dump JSON files, one per interface.
        margin_lsb: RID 9 send-period margin in 50 µs LSBs for the timeout branch.

    Returns:
        (list[CheckResult]) One RID cross-check result per capture, in load order.

    Raises:
        FileNotFoundError: If the directory holds no capture (propagated from the read).
    """
    return [
        check_rid_crosscheck(RidCrosscheck.confirmed(evaluation))
        for evaluation in reverify_from_fixture(fixture_dir, margin_lsb)
    ]
