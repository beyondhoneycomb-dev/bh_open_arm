"""The runaway detector — a publisher that gates policy output and holds on a fault.

SPINE §2-1: this detector is a **producer**, not a writer. It holds a
`MailboxProducer` and nothing that can reach CAN; when it decides to stop the arm it
does not write a hold frame and does not touch the scheduler's `SafetyLatch` — it
**publishes a hold intent** (the last valid pose, `qh`) to the mailbox, and the
committed `ActuationScheduler` turns that into the actual held frames. Living
publisher-side is deliberate: it keeps the detector off the Wave-1 gateway's files, so
the single-owner rule is never contested (`02c` §1.8 워크플로우 형상).

What it does each running tick, in order:

1. **Reject NaN/Inf** (`FR-INF-042`). LeRobot has no such check. A non-finite action
   is not sent; the last valid action is held and a counter advances. A single
   rejection does not fault — the policy may recover next tick.
2. **Dual-log** (`FR-INF-047`). Every tick records the raw request and the
   safety-gate-passed accepted action (SPINE §6), so a clamp keeps both and the raw
   request stays recoverable.
3. **Run the four runaway conditions** (`FR-INF-043`), each with its own counter so
   none masks another. Any one biting drives **P3 -> P8**: the action queue is
   discarded, a hold intent is published, the first trigger is recorded, and the
   error code is `OA-INF-003`.

Remote disconnects (`FR-INF-046`) enter the same P8 hold through `on_remote_health`,
which classifies transport vs empty-action (vs stale, vs queue-wait) to distinct error
codes and discards the queue so no stale action executes open-loop.

Once faulted the detector publishes only hold intents and refuses fresh policy output
until `acknowledge`, because `11` §4.3 forbids `P8 -> P3`: recovery must route through
an explicit operator act (P7). That refusal is the publisher-side "no auto-resume".
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from backend.actuation import JointLimit, MailboxProducer
from backend.inference.adapter import ActionChunkQueue, QueueMeter, action_vector_to_request
from backend.inference.runaway.conditions import (
    RUNAWAY_ERROR_CODE,
    ConditionSignals,
    RunawayCondition,
    RunawayConditions,
)
from backend.inference.runaway.disconnect import (
    DisconnectClass,
    RemoteHealth,
    classify_remote,
    error_code_for,
    is_network_disconnect,
)
from backend.inference.runaway.dual_log import DualActionRecord, DualActionRecorder
from backend.inference.runaway.phase import FaultKind, InferencePhase
from backend.inference.runaway.thresholds import RunawayThresholds
from contracts.action import (
    BIMANUAL_ACTION_DIM,
    AcceptedPositionAction,
    RequestedPositionAction,
)


@dataclass(frozen=True)
class ActionVerdict:
    """The outcome of one running-tick evaluation.

    Attributes:
        phase: The phase after this tick (RUNNING, or FAULT once a condition bit).
        published: The target published to the mailbox this tick — the raw request on
            a clean tick, or the hold intent on a NaN reject or a fault.
        is_hold_intent: Whether `published` is a hold intent rather than fresh output.
        nan_inf_rejected: Whether this tick's action was rejected as non-finite.
        triggered: The runaway conditions that bit this tick (empty on a clean tick).
        first_trigger: The recorded first trigger when a fault occurred, else None.
        error_code: The registry error code when a fault occurred, else None.
        record: The dual-log record for this tick (raw request always recoverable).
    """

    phase: InferencePhase
    published: RequestedPositionAction
    is_hold_intent: bool
    nan_inf_rejected: bool
    triggered: frozenset[RunawayCondition]
    first_trigger: RunawayCondition | None
    error_code: str | None
    record: DualActionRecord


@dataclass(frozen=True)
class DisconnectVerdict:
    """The outcome of one remote-health evaluation.

    Attributes:
        disconnect_class: The classified failure, or None when the remote is healthy.
        error_code: The registry error code for the class, or None when healthy.
        is_network: Whether the class is a network/session loss (False for a
            queue-wait timeout — not a network timeout, `FR-INF-046`).
        queue_residual_after: The action-queue residual after handling — 0 on any
            disconnect, because the queue is discarded (CG-4A-08e).
        hold_intent_published: Whether a hold intent was published this call.
    """

    disconnect_class: DisconnectClass | None
    error_code: str | None
    is_network: bool
    queue_residual_after: int
    hold_intent_published: bool


class RunawayDetector:
    """A publisher-side runaway detector, dual recorder, and remote-disconnect classifier.

    Ownership: holds a publish-only `MailboxProducer` (its only privilege — no CAN
    handle exists anywhere on it), the committed `QueueMeter` it reads the starvation
    ratio from, the four conditions, the dual recorder, and its own residual
    `ActionChunkQueue` (discarded on a fault so no stale action runs open-loop). It
    holds no scheduler and no latch: the hold it wants is expressed by *what it
    publishes*, not by reaching into the consumer.
    """

    def __init__(
        self,
        producer: MailboxProducer,
        meter: QueueMeter,
        thresholds: RunawayThresholds,
        initial_hold: RequestedPositionAction,
        joint_limits: tuple[JointLimit | None, ...] | None = None,
    ) -> None:
        """Wire the detector over a publish-only producer.

        Args:
            producer: The mailbox producer the detector publishes through; the
                committed scheduler reads the same mailbox and is the sole CAN writer.
            meter: The committed `QueueMeter` (WP-4A-07) whose exhaustion ratio feeds
                runaway condition ④.
            thresholds: The four `FR-INF-043` thresholds (parameters, not validated
                values in this band).
            initial_hold: The pose to hold at before any valid action is accepted
                (`qh` at start); its values seed the hold intent.
            joint_limits: The scheduler's per-joint limits, passed so the accepted
                action logged here equals the action the scheduler sends.
        """
        self._producer = producer
        self._meter = meter
        self._joint_limits = joint_limits
        self._conditions = RunawayConditions(thresholds)
        self._recorder = DualActionRecorder()
        self._queue = ActionChunkQueue()
        self._initial_hold = initial_hold
        self._hold_pose = initial_hold.values
        self._prev_requested: RequestedPositionAction | None = None
        self._phase = InferencePhase.RUNNING
        self._fault_kind: FaultKind | None = None
        self._fault_error_code: str | None = None
        self._first_trigger: RunawayCondition | None = None
        self._nan_inf_rejections = 0
        self._hold_intents_published = 0
        self._open_loop_ticks = 0
        self._last_published: RequestedPositionAction | None = None

    @property
    def phase(self) -> InferencePhase:
        """The current inference phase (RUNNING or FAULT)."""
        return self._phase

    @property
    def fault_kind(self) -> FaultKind | None:
        """Why the detector faulted (RUNAWAY / REMOTE_DISCONNECT), or None if running."""
        return self._fault_kind

    @property
    def fault_error_code(self) -> str | None:
        """The registry error code of the active fault, or None when running."""
        return self._fault_error_code

    @property
    def first_trigger(self) -> RunawayCondition | None:
        """The first runaway condition that tripped, or None (no runaway fault)."""
        return self._first_trigger

    @property
    def nan_inf_rejections(self) -> int:
        """Count of NaN/Inf actions rejected and held (`FR-INF-042`)."""
        return self._nan_inf_rejections

    @property
    def hold_intents_published(self) -> int:
        """Count of hold intents published to the mailbox."""
        return self._hold_intents_published

    @property
    def open_loop_execution_ticks(self) -> int:
        """Ticks that executed a queued action with no fresh observation — must stay 0.

        The detector has no code path that publishes from the residual queue: running
        ticks publish fresh policy output and faulted ticks publish hold intents, so
        this counter can only ever read 0. It is exposed so CG-4A-08e can assert that
        no open-loop execution occurred after a disconnect.
        """
        return self._open_loop_ticks

    @property
    def queue_residual(self) -> int:
        """Residual actions in the detector's own queue (0 after any fault discard)."""
        return self._queue.residual()

    @property
    def recorder(self) -> DualActionRecorder:
        """The dual recorder holding this episode's SPINE §6 records."""
        return self._recorder

    @property
    def conditions(self) -> RunawayConditions:
        """The four-condition evaluator (per-condition counters live here)."""
        return self._conditions

    @property
    def last_published(self) -> RequestedPositionAction | None:
        """The most recent target published to the mailbox, or None."""
        return self._last_published

    def load_queue(self, action_vectors: Sequence[Sequence[float]]) -> None:
        """Fill the residual action queue (models a remote chunk awaiting publication).

        Args:
            action_vectors: Ordered position vectors, each `BIMANUAL_ACTION_DIM` wide.
        """
        self._queue.push_chunk([action_vector_to_request(vector) for vector in action_vectors])

    def process_action(
        self, requested_vector: Sequence[float], ee_velocity: float | None = None
    ) -> ActionVerdict:
        """Gate one policy action: reject NaN/Inf, dual-log, run the four conditions.

        Args:
            requested_vector: The raw policy output, `BIMANUAL_ACTION_DIM` positions
                in degrees; may contain NaN/Inf (which is rejected, not sent).
            ee_velocity: The end-effector speed this tick for condition ③, or None
                when unmeasured.

        Returns:
            (ActionVerdict) What was published, the dual record, and any fault.

        Raises:
            ValueError: If `requested_vector` is not `BIMANUAL_ACTION_DIM` wide.
        """
        if len(requested_vector) != BIMANUAL_ACTION_DIM:
            raise ValueError(
                f"policy action must be {BIMANUAL_ACTION_DIM}-wide; got {len(requested_vector)}"
            )
        if self._phase is InferencePhase.FAULT:
            return self._faulted_tick()
        if not all(math.isfinite(component) for component in requested_vector):
            return self._reject_nan_inf(requested_vector)

        requested = action_vector_to_request(requested_vector)
        record = self._recorder.record(requested, self._joint_limits)
        signals = self._signals(requested, record, ee_velocity)
        biting = self._conditions.evaluate(signals)
        if biting:
            return self._enter_runaway(biting, record)

        self._producer.publish(requested)
        self._last_published = requested
        self._hold_pose = record.accepted.values
        self._prev_requested = requested
        return ActionVerdict(
            phase=InferencePhase.RUNNING,
            published=requested,
            is_hold_intent=False,
            nan_inf_rejected=False,
            triggered=frozenset(),
            first_trigger=None,
            error_code=None,
            record=record,
        )

    def on_remote_health(self, health: RemoteHealth) -> DisconnectVerdict:
        """Classify remote health; on any failure discard the queue and hold (`FR-INF-046`).

        A healthy remote returns a no-fault verdict and changes nothing. Any classified
        failure — transport, stale, empty-action, or queue-wait — discards the residual
        queue immediately (so no stale action executes open-loop), publishes a hold
        intent, and transitions to P8 with the class's distinct error code.

        Args:
            health: This tick's snapshotted remote signals.

        Returns:
            (DisconnectVerdict) The classification, its code, and the post-discard
            queue residual (0 on any disconnect).
        """
        disconnect_class = classify_remote(health)
        if disconnect_class is None:
            return DisconnectVerdict(
                disconnect_class=None,
                error_code=None,
                is_network=False,
                queue_residual_after=self._queue.residual(),
                hold_intent_published=False,
            )
        code = error_code_for(disconnect_class)
        self._enter_fault(FaultKind.REMOTE_DISCONNECT, code, first_trigger=None)
        self._publish_hold_intent()
        return DisconnectVerdict(
            disconnect_class=disconnect_class,
            error_code=code,
            is_network=is_network_disconnect(disconnect_class),
            queue_residual_after=self._queue.residual(),
            hold_intent_published=True,
        )

    def acknowledge(self) -> None:
        """Operator-acknowledge the fault, the only exit from P8 (`11` §4.3, via P7).

        Clears the fault so a subsequent `begin_episode` can resume; it is an explicit
        call, never automatic, which is the no-auto-resume guarantee. It does not by
        itself return to RUNNING — the full machine routes P8 -> P7 -> P2 -> P3.
        """
        self._phase = InferencePhase.RUNNING
        self._fault_kind = None
        self._fault_error_code = None
        self._first_trigger = None

    def begin_episode(self) -> None:
        """Reset per-episode state at episode start (`FR-INF-066`).

        Clears the conditions, the dual records, the residual queue, the fault, and the
        per-episode counters. The meter is the caller's (WP-4A-07) and is reset there.
        """
        self._conditions.reset()
        self._recorder.reset()
        self._queue.clear()
        self._phase = InferencePhase.RUNNING
        self._fault_kind = None
        self._fault_error_code = None
        self._first_trigger = None
        self._prev_requested = None
        self._hold_pose = self._initial_hold.values
        self._nan_inf_rejections = 0
        self._hold_intents_published = 0
        self._open_loop_ticks = 0
        self._last_published = None

    def _signals(
        self,
        requested: RequestedPositionAction,
        record: DualActionRecord,
        ee_velocity: float | None,
    ) -> ConditionSignals:
        """Derive the four condition signals from the request, the clamp, and the meter.

        Clip ratio is the fraction of joints the gate moved (requested vs accepted);
        delta-q is the largest per-tick joint jump against the previous request;
        starvation is the committed meter's exhaustion ratio; EE speed is passed
        through. Reading `.value` for the jump magnitude is arithmetic, not a unit
        reconstruction, so it stays within the CTR-UNIT contract.

        Args:
            requested: This tick's raw request.
            record: The dual record (its accepted action gives the clip ratio).
            ee_velocity: The EE speed this tick, or None.

        Returns:
            (ConditionSignals) The snapshotted signals for `RunawayConditions`.
        """
        clipped = sum(
            1
            for index in range(BIMANUAL_ACTION_DIM)
            if requested.values[index] != record.accepted.values[index]
        )
        clip_ratio = clipped / BIMANUAL_ACTION_DIM
        if self._prev_requested is None:
            delta_q = 0.0
        else:
            delta_q = max(
                abs((requested.values[index] - self._prev_requested.values[index]).value)
                for index in range(BIMANUAL_ACTION_DIM)
            )
        return ConditionSignals(
            clip_ratio=clip_ratio,
            delta_q=delta_q,
            ee_velocity=ee_velocity,
            starvation_ratio=self._meter.exhaustion_ratio,
        )

    def _enter_runaway(
        self, biting: frozenset[RunawayCondition], record: DualActionRecord
    ) -> ActionVerdict:
        """Transition to P8 on a runaway, recording the first trigger without masking.

        The offending request has already been dual-logged (raw recoverable). The
        first trigger is the deterministic pick among all conditions that bit; every
        biting condition's own counter has already advanced, so none is masked.

        Args:
            biting: The conditions that tripped this tick.
            record: The dual record of the offending request.

        Returns:
            (ActionVerdict) A FAULT verdict; the published target is the hold intent.
        """
        first_trigger = self._conditions.first_trigger(biting)
        self._enter_fault(FaultKind.RUNAWAY, RUNAWAY_ERROR_CODE, first_trigger)
        self._publish_hold_intent()
        return ActionVerdict(
            phase=InferencePhase.FAULT,
            published=self._hold_request(),
            is_hold_intent=True,
            nan_inf_rejected=False,
            triggered=biting,
            first_trigger=first_trigger,
            error_code=RUNAWAY_ERROR_CODE,
            record=record,
        )

    def _reject_nan_inf(self, requested_vector: Sequence[float]) -> ActionVerdict:
        """Reject a non-finite action: hold the last valid action, count it, do not fault.

        The raw (non-finite) request is still dual-logged so it stays recoverable, with
        the accepted channel set to the held last-valid pose — the request was not
        sent. A single rejection is not a P8: the policy may recover next tick.

        Args:
            requested_vector: The raw non-finite policy output.

        Returns:
            (ActionVerdict) A RUNNING verdict flagged `nan_inf_rejected`.
        """
        self._nan_inf_rejections += 1
        requested = action_vector_to_request(requested_vector)
        held = self._hold_request()
        record = self._recorder.record_held(
            requested, self._hold_accepted(), stale=False, latched=False
        )
        self._producer.publish(held)
        self._last_published = held
        return ActionVerdict(
            phase=InferencePhase.RUNNING,
            published=held,
            is_hold_intent=True,
            nan_inf_rejected=True,
            triggered=frozenset(),
            first_trigger=None,
            error_code=None,
            record=record,
        )

    def _faulted_tick(self) -> ActionVerdict:
        """Handle a tick while already in P8: publish a hold intent, accept no output.

        Returns:
            (ActionVerdict) A FAULT verdict carrying the hold intent; the fresh policy
            output is not evaluated and not sent (no auto-resume until acknowledged).
        """
        record = self._publish_hold_intent()
        return ActionVerdict(
            phase=InferencePhase.FAULT,
            published=self._hold_request(),
            is_hold_intent=True,
            nan_inf_rejected=False,
            triggered=frozenset(),
            first_trigger=self._first_trigger,
            error_code=self._fault_error_code,
            record=record,
        )

    def _enter_fault(
        self, kind: FaultKind, code: str, first_trigger: RunawayCondition | None
    ) -> None:
        """Latch into P8, keeping the first cause, and discard the action queue.

        Like the shared safety latch, the first cause wins: a fault already held is not
        overwritten by a later one, so the attribution names what first stopped the
        arm. The queue is discarded here — the single act that guarantees no stale
        action executes open-loop (`FR-INF-046`, `11` §4.3).

        Args:
            kind: Whether the fault is a runaway or a remote disconnect.
            code: The registry error code to record.
            first_trigger: The first runaway condition, or None for a disconnect.
        """
        self._queue.clear()
        if self._phase is InferencePhase.FAULT:
            return
        self._phase = InferencePhase.FAULT
        self._fault_kind = kind
        self._fault_error_code = code
        self._first_trigger = first_trigger

    def _publish_hold_intent(self) -> DualActionRecord:
        """Publish the hold intent (`qh`) to the mailbox and dual-log it as a latched hold.

        The hold intent is the last valid pose, published as a fresh request the
        scheduler re-commands — a hold-in-place. The detector never writes the hold
        frame; the scheduler does (SPINE §2-1).

        Returns:
            (DualActionRecord) The record of the published hold intent.
        """
        hold = self._hold_request()
        record = self._recorder.record(hold, self._joint_limits, latched=True)
        self._producer.publish(hold)
        self._last_published = hold
        self._hold_intents_published += 1
        return record

    def _hold_request(self) -> RequestedPositionAction:
        """Build the hold-intent request from the current hold pose (`qh`)."""
        return RequestedPositionAction(values=self._hold_pose)

    def _hold_accepted(self) -> AcceptedPositionAction:
        """Return the held pose as an accepted action, for the NaN-reject record.

        The held action is the last valid accepted pose (already within limits), so it
        is its own accepted value without re-clamping.
        """
        return AcceptedPositionAction(values=self._hold_pose)
