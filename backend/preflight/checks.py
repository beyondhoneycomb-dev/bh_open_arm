"""The five torque-ON precondition checks — each blocks, none warns.

Every check reuses the primitive the corresponding Wave-0/Wave-1 WP already built and
adds only the torque-ON *decision* on top of it: it does not re-implement the RID limit
comparison (`WP-0B-07`), the CAN-FD link verifier (`WP-0B-02`), the writer lock
(`WP-0B-01`), the `Side` contract (`CTR-PLUG`), or the two-stage clamp validation
(`WP-2A-03`/`WP-1-03`). The new behaviour here is the reduction of each primitive's
report to a single "may torque be enabled?" verdict, fail-closed on every ambiguity.

The RID gate is the one non-trivial reduction. `evaluate_dump` judges a read but does
not itself yield a torque verdict, so `_rid_torque_gate` folds three of its judgments —
the per-motor RID 21/22/23 comparison (`03` FR-MOT-003), the RID 9 completeness gate
(`PG-RID-001`: a partial read forbids torque-ON), and the J7 TMAX judgment (`PG-J7-001`)
— into one block-or-pass, and blocks unless every one of them clears.
"""

from __future__ import annotations

from backend.actuation import SafetyConfigError, SafetyLimits
from backend.can.link import LinkState, validate_link
from backend.can.lock import LockState
from backend.can.rid.evaluate import DumpEvaluation
from backend.can.rid.judge import PgStatus
from backend.preflight.model import CheckResult, PreflightCheck, RidCrosscheck
from contracts.plugin.config import Side


def _rid_torque_gate(evaluation: DumpEvaluation) -> tuple[bool, str]:
    """Reduce a judged RID read to a single torque-ON verdict (`03` FR-MOT-003).

    Torque-ON is permitted only when every read motor's RID 21/22/23 matched
    `MOTOR_LIMIT_PARAMS`, the RID 9 read covered every expected motor (a partial read
    is `PG-RID-001` FAIL_BLOCKING — read failure forbids torque-ON), and, when J7's
    TMAX was read, it classified as DM4310 (`PG-J7-001`). Every disagreement is
    collected so the block names all of them, not just the first.

    Args:
        evaluation: The judged read from `backend.can.rid.evaluate.evaluate_dump`.

    Returns:
        (tuple[bool, str]) `(passed, detail)`; passed is True only when no cause blocks.
    """
    causes: list[str] = []
    for motor in evaluation.per_motor:
        if motor.limits is None:
            causes.append(f"motor 0x{motor.motor_id:02x}: RID 21/22/23 not fully read")
            continue
        for field in motor.limits.mismatches():
            causes.append(
                f"motor 0x{motor.motor_id:02x} RID {field.rid} {field.field}: "
                f"expected {field.expected}, got {field.actual}"
            )
    if evaluation.rid9.status is PgStatus.FAIL_BLOCKING:
        missing = ", ".join(f"0x{mid:02x}" for mid in evaluation.rid9.missing_motor_ids)
        causes.append(f"RID 9 partial read (PG-RID-001): missing motors {missing}")
    if evaluation.j7 is not None and evaluation.j7.status is PgStatus.FAIL_BLOCKING:
        causes.append(
            f"J7 TMAX {evaluation.j7.measured_tmax} classifies "
            f"{evaluation.j7.classified_type}, expected {evaluation.j7.expected_type} (PG-J7-001)"
        )
    if causes:
        return False, "RID 21/22/23 cross-check mismatch: " + "; ".join(causes)
    read = len(evaluation.per_motor)
    return True, f"RID 21/22/23 matched MOTOR_LIMIT_PARAMS on {read} motor(s) of {evaluation.iface}"


def check_rid_crosscheck(evidence: RidCrosscheck) -> CheckResult:
    """① Block torque-ON unless a confirmed RID read matches `MOTOR_LIMIT_PARAMS`.

    An unavailable cross-check (no confirmed read — the live sixteen-motor read is
    hardware-deferred) is fail-closed: it blocks, because torque-ON on unverified
    position/speed/torque scaling is the exact hazard `03` FR-MOT-003 / `12` FR-SAF-004
    forbid.

    Args:
        evidence: The confirmed-or-unavailable RID cross-check evidence.

    Returns:
        (CheckResult) Passed only on a confirmed, fully matching read.
    """
    if evidence.evaluation is None:
        return CheckResult(
            check=PreflightCheck.RID_CROSSCHECK,
            passed=False,
            detail=(
                f"RID cross-check unavailable ({evidence.unavailable_reason}); "
                "torque-ON blocked until the RID 21/22/23 read is confirmed (03 FR-MOT-003)"
            ),
        )
    passed, detail = _rid_torque_gate(evidence.evaluation)
    return CheckResult(check=PreflightCheck.RID_CROSSCHECK, passed=passed, detail=detail)


def check_side(side: Side | None) -> CheckResult:
    """② Block startup when the arm side is unspecified (`12` FR-SAF-070).

    An unset side leaves LeRobot's ±5° default limits in force, so the arm silently
    does not move (`01` FR-SYS-013); the failure is quiet, which is why it must block
    rather than warn.

    Args:
        side: The selected arm side, or None when `--robot.side` was not given.

    Returns:
        (CheckResult) Passed only when a concrete `Side` was selected.
    """
    if not isinstance(side, Side):
        return CheckResult(
            check=PreflightCheck.SIDE_SPECIFIED,
            passed=False,
            detail=(
                "side unspecified; --robot.side=left|right is required — the ±5° default is "
                "unusable and fails silently (12 FR-SAF-070, 01 FR-SYS-013)"
            ),
        )
    return CheckResult(
        check=PreflightCheck.SIDE_SPECIFIED, passed=True, detail=f"side = {side.value}"
    )


def check_can_fd(link: LinkState | None) -> CheckResult:
    """③ Block startup unless the link is CAN-FD at the required rates (`01` FR-SYS-006).

    Reuses the `WP-0B-02` verifier verbatim: `validate_link` fails when `fd` is off,
    the bitrate/dbitrate are wrong, or the bus is not `ERROR-ACTIVE`. A CAN-2.0 link
    opened `fd=True` "succeeds" yet breaks communication silently (`01` §2.18 trap 5),
    so an unverified link must block torque-ON, not warn.

    Args:
        link: The parsed `ip -details link show` state, or None when it could not be
            read or parsed.

    Returns:
        (CheckResult) Passed only when every FR-SYS-006 criterion holds.
    """
    if link is None:
        return CheckResult(
            check=PreflightCheck.CAN_FD_LINK,
            passed=False,
            detail="link state unread; `ip -details link show` could not be parsed (01 FR-SYS-006)",
        )
    verdict = validate_link(link)
    if not verdict.ok:
        return CheckResult(
            check=PreflightCheck.CAN_FD_LINK,
            passed=False,
            detail="CAN-FD link not verified: " + "; ".join(str(m) for m in verdict.mismatches),
        )
    return CheckResult(
        check=PreflightCheck.CAN_FD_LINK,
        passed=True,
        detail=f"link {link.iface}: fd on, {link.bitrate}/{link.dbitrate}, {link.state}",
    )


def check_writer_lock(state: LockState) -> CheckResult:
    """④ Block torque-ON unless this process holds the writer lock (`02` FR-CON-010).

    Torque-ON requires the `WP-0B-01` exclusive writer lock to be held by *this*
    process. A foreign holder blocks with its PID named (the refusal contract of
    `01` FR-SYS-005 / `02` FR-CON-010); a free-but-unheld lock also blocks, because a
    session that never acquired the lock must not drive the bus.

    Args:
        state: The lock state for the interface, from `LockManager.lock_state`.

    Returns:
        (CheckResult) Passed only when the lock is held by this process.
    """
    if state.held_by_self:
        return CheckResult(
            check=PreflightCheck.WRITER_LOCK,
            passed=True,
            detail=f"writer lock {state.iface} held by this process",
        )
    if state.holder is not None:
        return CheckResult(
            check=PreflightCheck.WRITER_LOCK,
            passed=False,
            detail=(
                f"writer lock {state.iface} held by another process: holder PID "
                f"{state.holder.holder_pid} ({state.holder.holder_cmdline}); torque-ON refused"
            ),
        )
    return CheckResult(
        check=PreflightCheck.WRITER_LOCK,
        passed=False,
        detail=(
            f"writer lock {state.iface} not held by this process; torque-ON requires the "
            "WP-0B-01 exclusive lock acquired before connect (02 FR-CON-010)"
        ),
    )


def check_clamp_canon(canon: SafetyLimits | None) -> CheckResult:
    """⑤ Refuse torque-ON when no valid canonical clamp limit set is selected.

    The canonical limit set (`12` FR-SAF-045) is the clamp envelope torque-ON runs
    inside. If none is selected (None) there is nothing to clamp against, so torque is
    refused; if one is selected it must pass the two-stage clamp validation (`WP-2A-03`
    reused via `SafetyLimits.validate`) — an operational envelope wider than mechanical,
    a torque above peak, or a collapsed rate guard refuses just as an unset canon does.

    Args:
        canon: The selected canonical clamp limit set, or None when unselected.

    Returns:
        (CheckResult) Passed only when a valid canon is selected.
    """
    if canon is None:
        return CheckResult(
            check=PreflightCheck.CLAMP_CANON,
            passed=False,
            detail=(
                "clamp-canon unselected; a canonical clamp limit set must be chosen before "
                "torque-ON (12 FR-SAF-045)"
            ),
        )
    try:
        canon.validate()
    except SafetyConfigError as exc:
        return CheckResult(
            check=PreflightCheck.CLAMP_CANON,
            passed=False,
            detail=f"clamp-canon invalid ({exc.reason.name}): {exc}",
        )
    return CheckResult(
        check=PreflightCheck.CLAMP_CANON,
        passed=True,
        detail=f"clamp-canon selected: {canon.width}-joint envelope validated",
    )
