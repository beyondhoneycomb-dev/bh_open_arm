"""The audit ring buffer — a time-bounded window that blocks an offset fault and dumps on a stop.

WP-2A-05. The ring retains the last `horizon_sec` (default 10 s, `04` FR-MAN-058) of
`AuditRecord`s — request, accepted, executed MIT command, safety override, and the
calibration transform chain — and does two active jobs beyond retention:

- **Block an offset double-add / miss immediately.** Every recorded chain is checked
  the instant it lands; a chain that applied the offset the wrong number of times, or
  whose motor angle does not match its declared applications, engages the safety latch
  and raises. The command is stopped, not merely logged (`04` FR-MAN-058, `02`
  FR-CON-033).
- **Dump on a safe-stop or collision.** `on_safety_event` snapshots the whole retained
  window so the moments before a latch survive for post-event analysis (`12` FR-SAF-065).

Ownership and reuse: the ring holds **no** latch of its own. It detects, then calls
back to engage the Wave-1 `SafetyLatch` through the scheduler — the same detection-only,
call-to-latch shape the `CollisionGuard` uses (`12` FR-SAF-074). The request/accepted
recording rule is likewise the Wave-1 `GateFrame`'s, embedded in each `AuditRecord`, not
re-implemented here. The retention clock is supplied per record (`AuditRecord.at`), so the
ring stays agnostic to the monotonic clock the scheduler owns.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from backend.audit.record import AuditRecord
from backend.audit.transform import (
    DECISION_A_OFFSET_APPLICATIONS,
    OFFSET_RESIDUAL_TOLERANCE_RAD,
    OffsetIntegrityError,
    OffsetVerdict,
    check_chain,
)
from ops.cancel.scheduler import LatchReason

# Default retention window: the last ten seconds of records (`04` FR-MAN-058).
DEFAULT_HORIZON_SEC = 10.0

# The latch-engage state pair for an offset fault, matching the guard's own
# PASS→LATCHED transition wording so the dump reads uniformly across latch sources.
_STATE_PASS = "PASS"
_STATE_LATCHED = "LATCHED"


@dataclass(frozen=True)
class AuditDump:
    """An immutable snapshot of the ring at a safe-stop or collision.

    Attributes:
        records: Every record retained when the dump was taken, oldest first.
        trigger: The latch reason that caused the dump (collision, lease expiry, …).
        dumped_at: The trigger's monotonic timestamp, seconds.
    """

    records: tuple[AuditRecord, ...]
    trigger: LatchReason
    dumped_at: float

    @property
    def span_sec(self) -> float:
        """The monotonic span the dump covers, newest minus oldest record time.

        Returns:
            (float) Retained span in seconds; 0.0 when fewer than two records.
        """
        if len(self.records) < 2:
            return 0.0
        return self.records[-1].at - self.records[0].at


class AuditRingBuffer:
    """A time-windowed audit recorder that blocks an offset fault and dumps on a stop.

    Ownership: holds the retained records and, optionally, a callback that engages the
    scheduler's safety latch on an offset fault. It owns no latch and no CAN handle —
    on a fault it calls back exactly as the `CollisionGuard` does, so there is one latch,
    not two.
    """

    def __init__(
        self,
        horizon_sec: float = DEFAULT_HORIZON_SEC,
        expected_offset_applications: int = DECISION_A_OFFSET_APPLICATIONS,
        offset_tolerance_rad: float = OFFSET_RESIDUAL_TOLERANCE_RAD,
        on_integrity_fault: Callable[[LatchReason], None] | None = None,
    ) -> None:
        """Configure the window and the offset-integrity policy.

        Args:
            horizon_sec: Retention window; records older than this behind the newest
                are evicted. Defaults to ten seconds.
            expected_offset_applications: How many times the calibration offset should
                be applied per joint (0 under convention a, `02` §2.9).
            offset_tolerance_rad: Slack for the offset residual check.
            on_integrity_fault: Engages the scheduler's safety latch when an offset
                fault is recorded; the ring calls this instead of holding a latch. When
                None, a fault still raises — the raise is the non-bypassable block — but
                no latch is engaged, so a caller that wants the arm held must supply it.
        """
        self._horizon_sec = horizon_sec
        self._expected_offset_applications = expected_offset_applications
        self._offset_tolerance_rad = offset_tolerance_rad
        self._on_integrity_fault = on_integrity_fault
        self._records: deque[AuditRecord] = deque()

    @property
    def horizon_sec(self) -> float:
        """The retention window, in seconds."""
        return self._horizon_sec

    @property
    def records(self) -> tuple[AuditRecord, ...]:
        """The retained records, oldest first."""
        return tuple(self._records)

    @property
    def span_sec(self) -> float:
        """The monotonic span currently retained, newest minus oldest record time.

        Returns:
            (float) Retained span in seconds; 0.0 when fewer than two records.
        """
        if len(self._records) < 2:
            return 0.0
        return self._records[-1].at - self._records[0].at

    def record(self, entry: AuditRecord) -> None:
        """Append one tick's record, evict the stale tail, then block an offset fault.

        The record is appended before the check so a faulting chain is present in the
        dump that a resulting latch will trigger — the evidence for the stop is retained,
        not discarded with the exception.

        Args:
            entry: The tick's audit record.

        Raises:
            OffsetIntegrityError: If the transform chain double-added or missed the
                offset. The safety latch is engaged first (when a callback is wired),
                so the arm is already held when the exception unwinds the command.
        """
        self._records.append(entry)
        self._evict_stale()
        verdict = check_chain(
            entry.chain,
            self._expected_offset_applications,
            self._offset_tolerance_rad,
        )
        if not verdict.ok:
            self._raise_offset_fault(verdict, entry.at)

    def on_safety_event(self, reason: LatchReason) -> AuditDump:
        """Snapshot the retained window in response to a safe-stop or collision.

        Registered by the harness so a guard latch or a deadman-lease expiry dumps the
        ring (`12` FR-SAF-065). Taking a snapshot leaves the window intact — recording
        continues, and a later event dumps again.

        Args:
            reason: The latch reason for the stop, carried into the dump.

        Returns:
            (AuditDump) The retained records with the trigger and its timestamp.
        """
        return AuditDump(
            records=tuple(self._records),
            trigger=reason,
            dumped_at=reason.latched_at,
        )

    def _evict_stale(self) -> None:
        """Drop records older than the horizon behind the newest retained record."""
        newest_at = self._records[-1].at
        while self._records and newest_at - self._records[0].at > self._horizon_sec:
            self._records.popleft()

    def _raise_offset_fault(self, verdict: OffsetVerdict, at: float) -> None:
        """Engage the latch (if wired) for an offset fault, then raise to block the command."""
        if self._on_integrity_fault is not None:
            fault = verdict.fault.value if verdict.fault else "fault"
            self._on_integrity_fault(
                LatchReason(
                    gate_id=f"AUDIT_OFFSET:{fault}:j{verdict.joint_index}",
                    previous_state=_STATE_PASS,
                    new_state=_STATE_LATCHED,
                    latched_at=at,
                )
            )
        raise OffsetIntegrityError(verdict)
