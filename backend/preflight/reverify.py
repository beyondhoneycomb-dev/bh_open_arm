"""Re-verification hook for the deferred item: the *live* RID cross-check (plan 02a §4.1).

Four of the five preconditions run in full on this host — side, CAN-FD link, writer
lock, and clamp-canon need no motors. The fifth, the RID 21/22/23 cross-check, runs its
*gate logic* here on synthetic reads, but its *live* form needs every fitted motor
powered with torque OFF asserted first (`12` FR-SAF-075), which this host cannot supply.
That live read is deferred — SKIPPED WITH A REASON in the bound test, never asserted
green — and wired to this hook, which re-runs the identical torque gate against real
captured bytes the moment a capture directory is supplied via `OPENARM_RID_REAL_FIXTURE`.

The read and judgment are reused wholesale from `backend.can.rid.reverify`
(`WP-0B-07`); this module only re-applies the WP-2A-09 torque gate to each real
evaluation, so the deferred acceptance re-runs the exact code the offline gate tests
exercise, now pointed at real motors.

Which motors a capture must cover is the fitted set, not the eight-motor registration
`ARM_SEND_IDS`. The two differ on a build whose tool puts no motor on `0x08`, and
judging such a capture against eight turns a fact about the build into a read failure
on every channel — a torque-ON refusal no capture from that rig could ever clear.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from backend.can.rid.reverify import (
    DEFAULT_MARGIN_LSB,
    FIXTURE_ENV_VAR,
    fixture_dir_from_env,
    reverify_from_fixture,
)
from backend.endeffector import default_profile
from backend.preflight.checks import check_rid_crosscheck
from backend.preflight.model import CheckResult, RidCrosscheck

__all__ = [
    "DEFAULT_MARGIN_LSB",
    "FIXTURE_ENV_VAR",
    "fixture_dir_from_env",
    "reverify_rid_crosscheck",
]


def reverify_rid_crosscheck(
    fixture_dir: Path,
    margin_lsb: int = DEFAULT_MARGIN_LSB,
    expected_motor_ids: Sequence[int] | None = None,
) -> list[CheckResult]:
    """Re-run the RID torque gate against real captured dumps, one per interface.

    Loads and judges every capture through `backend.can.rid.reverify.reverify_from_fixture`
    — the same decode, RID 9, RID 21/22/23 and J7 judgments the offline path uses — then
    applies `check_rid_crosscheck` to each. This is the re-verification the deferred live
    RID cross-check requires.

    Args:
        fixture_dir: Directory of captured RID dump JSON files, one per interface.
        margin_lsb: RID 9 send-period margin in 50 µs LSBs for the timeout branch.
        expected_motor_ids: The motors the arm actually has. Defaults to the ids the
            fitted tool puts on the bus (`default_profile().motor_send_ids`) — an arm whose
            tool has no gripper motor carries seven, and demanding an answer from `0x08`
            makes the acceptance unclearable on that rig rather than strict.

    Returns:
        (list[CheckResult]) One RID cross-check result per capture, in load order.

    Raises:
        FileNotFoundError: If the directory holds no capture (propagated from the read).
    """
    fitted = default_profile().motor_send_ids if expected_motor_ids is None else expected_motor_ids
    return [
        check_rid_crosscheck(RidCrosscheck.confirmed(evaluation))
        for evaluation in reverify_from_fixture(fixture_dir, margin_lsb, fitted)
    ]
