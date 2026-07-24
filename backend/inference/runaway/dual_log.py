"""The dual recorder — SPINE §6 action contract verbatim, raw request always recoverable.

`FR-INF-047` is the decisive invariant of this WP: record **both** the policy's raw
output and the safety-gate-passed action that was actually sent. `send_action`
returns the post-clip value (`openarm_follower.py:344`), so a recorder that kept only
the accepted action would erase what the policy *asked for* — and 4C's failure
taxonomy could then never tell "the policy was bad" from "the gate clamped it". So a
clamp where requested != accepted keeps both, and the raw request stays recoverable.

The record implements SPINE §6's four action channels **verbatim** — no invented
field:

- `requested` = `requestedPositionAction[16]`, the raw policy output (pre-clamp).
- `accepted` = `acceptedPositionAction[16]`, the post-gate action — the LeRobot
  dataset `action`, position-only (`FR-TRN-066`), the *sole* training target here.
- `executed_mit` = `executedMitCommand` (kp/kd/q/dq/tau), **AUDIT ONLY**. Safety and
  gravity torque ride this separate execution+audit channel and must never mix into
  the training target; `training_target` returns the accepted position action and
  cannot reach `executed_mit`, which is what keeps the training path from reading it.
- `safety_override` = `safetyOverride` + clamp reason + stale-source + latch flags.

The clamp is the committed `clamp_request` (`backend.actuation.gateway`), applied
with the *same* joint limits the scheduler uses, so the accepted action this recorder
logs is byte-identical to the one the scheduler sends — the log is authoritative, not
a second, drifting computation.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from backend.actuation import JointLimit, clamp_request
from contracts.action import (
    AcceptedPositionAction,
    ClampReason,
    ExecutedMitCommand,
    RequestedPositionAction,
    SafetyOverride,
)

# Rolling window of dual records kept for the live audit view; a rollout is
# arbitrarily long, so the retained window is bounded while the per-tick record
# still lands in the structured log stream. Post-analysis reads the log stream, not
# this in-memory window, so bounding it loses nothing recoverable.
DUAL_RECORD_WINDOW = 4096


@dataclass(frozen=True)
class DualActionRecord:
    """One tick's SPINE §6 action channels, raw request preserved beside the sent action.

    Attributes:
        requested: `requestedPositionAction[16]` — the raw policy output, pre-clamp.
        accepted: `acceptedPositionAction[16]` — the post-gate action actually sent,
            position-only; the only training target among these channels.
        safety_override: `safetyOverride` — override flag, clamp reason, stale-source
            and latch flags explaining any difference between requested and accepted.
        executed_mit: `executedMitCommand` (kp/kd/q/dq/tau), AUDIT ONLY; None when the
            downstream scheduler emission has not been attached. Never a training input.
    """

    requested: RequestedPositionAction
    accepted: AcceptedPositionAction
    safety_override: SafetyOverride
    executed_mit: tuple[ExecutedMitCommand, ...] | None = None

    @property
    def clamp_detected(self) -> bool:
        """Whether the gate altered the request (requested != accepted).

        Returns:
            (bool) True when at least one joint's accepted angle differs from the
            request — the CG-4A-08c case that must keep both values.
        """
        return self.requested.values != self.accepted.values

    def training_target(self) -> AcceptedPositionAction:
        """Return the sole training target: the accepted position action.

        This is the one channel the training path may read. It deliberately cannot
        reach `executed_mit`: safety/gravity torque is an audit-only channel (SPINE
        §6) and mixing it into the target would train a head on forces the policy
        never commanded.

        Returns:
            (AcceptedPositionAction) The post-gate, position-only dataset action.
        """
        return self.accepted


class DualActionRecorder:
    """Builds and retains SPINE §6 dual records; the raw request is always kept.

    Ownership: the detector holds one recorder per episode. It clamps each raw
    request through the committed `clamp_request` with the scheduler's joint limits,
    composes the `safetyOverride`, stores the record in a bounded window, and hands it
    back so the caller can drive the runaway conditions off the same accepted action.
    """

    def __init__(self, window: int = DUAL_RECORD_WINDOW) -> None:
        """Start an empty recorder.

        Args:
            window: Rolling number of records retained in memory.
        """
        self._records: deque[DualActionRecord] = deque(maxlen=window)

    @property
    def records(self) -> tuple[DualActionRecord, ...]:
        """The retained dual records, oldest first.

        Returns:
            (tuple[DualActionRecord, ...]) The rolling window of records.
        """
        return tuple(self._records)

    @property
    def last(self) -> DualActionRecord | None:
        """The most recent dual record, or None before any tick.

        Returns:
            (DualActionRecord | None) The last record.
        """
        return self._records[-1] if self._records else None

    def record(
        self,
        requested: RequestedPositionAction,
        joint_limits: tuple[JointLimit | None, ...] | None,
        stale: bool = False,
        latched: bool = False,
        executed_mit: tuple[ExecutedMitCommand, ...] | None = None,
    ) -> DualActionRecord:
        """Clamp a raw request, compose the override, store and return the dual record.

        Args:
            requested: The raw policy output (`requestedPositionAction`).
            joint_limits: The scheduler's per-joint limits (same instance the
                scheduler clamps with, so the accepted action matches what it sends).
            stale: Whether the source was stale this tick (stale-source flag).
            latched: Whether a safety latch / P8 hold is held this tick (latch flag).
            executed_mit: The scheduler's emitted MIT batch, attached for audit only;
                None when not observed at record time.

        Returns:
            (DualActionRecord) The record just stored, raw request recoverable.
        """
        accepted, clamp_override = clamp_request(requested, joint_limits)
        override = self._compose_override(clamp_override.clamp_reason, stale, latched)
        record = DualActionRecord(
            requested=requested,
            accepted=accepted,
            safety_override=override,
            executed_mit=executed_mit,
        )
        self._records.append(record)
        return record

    def record_held(
        self,
        requested: RequestedPositionAction,
        accepted: AcceptedPositionAction,
        stale: bool = False,
        latched: bool = False,
        executed_mit: tuple[ExecutedMitCommand, ...] | None = None,
    ) -> DualActionRecord:
        """Record a tick whose sent action was a held pose, not a clamp of the request.

        This is the NaN/Inf-rejection and open-hold path (`FR-INF-042`): the raw
        request is still preserved for recovery, but the accepted (sent) action is the
        last valid held pose rather than a clamp of the request, because a non-finite
        request has no meaningful clamp. `override_active` is set when the sent action
        differs from the request; the reason is not a clamp reason (the frozen
        `ClampReason` enumerates clamps, not outlier rejection — that is tracked by the
        detector's own counter).

        Args:
            requested: The raw policy output (preserved even when non-finite).
            accepted: The held pose actually sent this tick.
            stale: Whether the source was stale this tick.
            latched: Whether a P8 hold is held this tick.
            executed_mit: Audit-only MIT batch, or None.

        Returns:
            (DualActionRecord) The stored record, raw request recoverable.
        """
        overridden = requested.values != accepted.values
        override = self._compose_override(ClampReason.NONE, stale, latched, overridden=overridden)
        record = DualActionRecord(
            requested=requested,
            accepted=accepted,
            safety_override=override,
            executed_mit=executed_mit,
        )
        self._records.append(record)
        return record

    def reset(self) -> None:
        """Drop the retained window (episode start)."""
        self._records.clear()

    def _compose_override(
        self, clamp_reason: ClampReason, stale: bool, latched: bool, overridden: bool = False
    ) -> SafetyOverride:
        """Fold the clamp reason together with the detector's stale/latch state.

        A latch outranks staleness outranks a joint-limit clamp for the recorded
        reason, because a latched hold is the most specific attribution of why the
        accepted action left the request; the boolean flags stay independently
        readable regardless of which reason won.

        Args:
            clamp_reason: The reason `clamp_request` reported.
            stale: Whether the source was stale this tick.
            latched: Whether a latch / P8 hold is held this tick.
            overridden: Whether the sent action differs from the request for a reason
                that is not a clamp (an outlier rejection), forcing `override_active`.

        Returns:
            (SafetyOverride) The composed override record.
        """
        if latched:
            reason = ClampReason.SAFETY_LATCH
        elif stale:
            reason = ClampReason.STALE_SOURCE
        else:
            reason = clamp_reason
        active = latched or stale or overridden or reason is not ClampReason.NONE
        return SafetyOverride(
            override_active=active, clamp_reason=reason, stale=stale, latched=latched
        )
