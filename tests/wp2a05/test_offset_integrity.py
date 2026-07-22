"""Acceptance ② (CG-2A-05b) — an offset double-add / miss is caught and blocked at once.

Recording a transform chain runs the offset-integrity check on the spot. A chain that
applied the calibration offset the wrong number of times — or whose motor angle does
not match its declared application count — raises immediately and engages the Wave-1
safety latch, so the command is stopped, not merely logged. The block is proven against
the real `SafetyLatch` and end-to-end against a real `ActuationScheduler` whose next tick
holds; nothing here is a vacuous green.

Convention (a) (`02` §2.9) makes the declared offset zero and its expected application
count zero, so a double-add is numerically invisible — the structural count is what
catches it. Option (b) (expected count one, non-zero offset) is exercised too, where a
miss and a value baked in without its counter are the failure shapes.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from backend.actuation import (
    MIT_BATCH_WIDTH,
    ActuationScheduler,
    EmissionLabel,
    GateResult,
    LeaseManager,
    MailboxProducer,
    ManualClock,
    SafetyLatch,
    TargetMailbox,
    TickTrace,
)
from backend.audit import (
    AuditRingBuffer,
    JointTransform,
    OffsetFault,
    OffsetIntegrityError,
    check_chain,
)
from contracts.action import ExecutedMitCommand
from contracts.units import Deg, Rad
from tests.wp2a05.conftest import clean_chain, filled, make_gateway, record_from

LEASE_DURATION_SEC = 0.1
OPTION_B_OFFSET_RAD = 0.1


def _corrupt(
    chain: tuple[JointTransform, ...], index: int, **overrides: Any
) -> tuple[JointTransform, ...]:
    """Return a copy of a chain with one joint's fields overridden."""
    joints = list(chain)
    joints[index] = replace(joints[index], **overrides)
    return tuple(joints)


def _clean_decision() -> tuple[GateResult, tuple[Deg, ...]]:
    """Run one clean gateway decision and return (result, requested)."""
    gateway, _guard = make_gateway()
    request = filled(10.0)
    return gateway.submit(request, filled(10.0)), request


def test_clean_chain_records_without_blocking() -> None:
    """A chain that applied the offset the declared number of times records and passes (②)."""
    result, request = _clean_decision()
    ring = AuditRingBuffer()

    ring.record(record_from(result, request, tick_index=0, at=0.0))

    assert len(ring.records) == 1


def test_double_add_is_caught_and_blocks() -> None:
    """An extra offset application (count above expected) raises DOUBLE_ADD (②)."""
    result, request = _clean_decision()
    ring = AuditRingBuffer()  # expected applications = 0 (convention a)
    # A double-add of a zero offset is numerically invisible; the count catches it.
    chain = _corrupt(clean_chain(result.accepted), 0, offset_applications=1)

    with pytest.raises(OffsetIntegrityError) as caught:
        ring.record(record_from(result, request, tick_index=0, at=0.0, chain=chain))

    assert caught.value.verdict.fault is OffsetFault.DOUBLE_ADD
    assert caught.value.verdict.joint_index == 0
    # The offending record is retained — the dump after the stop must hold the evidence.
    assert len(ring.records) == 1


def test_missed_application_is_caught_and_blocks() -> None:
    """A dropped offset application (count below expected) raises MISSED (②)."""
    result, request = _clean_decision()
    ring = AuditRingBuffer(expected_offset_applications=1)
    clean = clean_chain(result.accepted, offset_rad=OPTION_B_OFFSET_RAD, applications=1)
    # Joint 0 forgot to add the offset: count 0 and q_motor back at q_user.
    missed = _corrupt(
        clean,
        0,
        offset_applications=0,
        q_motor_rad=clean[0].q_user_rad,
    )

    with pytest.raises(OffsetIntegrityError) as caught:
        ring.record(record_from(result, request, tick_index=0, at=0.0, chain=missed))

    assert caught.value.verdict.fault is OffsetFault.MISSED


def test_value_baked_in_without_its_counter_is_caught() -> None:
    """A double-added value whose counter still reads one raises RESIDUAL_MISMATCH (②)."""
    result, request = _clean_decision()
    ring = AuditRingBuffer(expected_offset_applications=1)
    clean = clean_chain(result.accepted, offset_rad=OPTION_B_OFFSET_RAD, applications=1)
    # The counter says one application, but the motor angle carries two offsets — the
    # arithmetic and the count disagree, which the residual axis exists to catch.
    sneaky = _corrupt(
        clean,
        0,
        q_motor_rad=Rad(clean[0].q_user_rad.value + 2 * OPTION_B_OFFSET_RAD),
    )

    with pytest.raises(OffsetIntegrityError) as caught:
        ring.record(record_from(result, request, tick_index=0, at=0.0, chain=sneaky))

    assert caught.value.verdict.fault is OffsetFault.RESIDUAL_MISMATCH


def test_a_fault_engages_the_wave1_safety_latch() -> None:
    """The ring blocks by engaging the real Wave-1 SafetyLatch, not a latch of its own (②)."""
    latch = SafetyLatch()
    result, request = _clean_decision()
    ring = AuditRingBuffer(on_integrity_fault=latch.engage)
    chain = _corrupt(clean_chain(result.accepted), 0, offset_applications=2)

    # Snapshot the pre-fault state into a local: asserting on the property directly
    # would narrow it, and mypy cannot see the callback engage the latch across the
    # opaque `with` block, so the post-fault assert would read as unreachable.
    started_active = latch.is_active
    assert not started_active
    with pytest.raises(OffsetIntegrityError):
        ring.record(record_from(result, request, tick_index=0, at=0.0, chain=chain))

    assert latch.is_active
    assert latch.reason is not None
    assert latch.reason.gate_id.startswith("AUDIT_OFFSET:")


def test_block_holds_the_arm_on_the_next_scheduler_tick() -> None:
    """End to end: after the offset fault the scheduler's next tick emits a latch hold (②)."""
    mailbox = TargetMailbox()
    clock = ManualClock()
    scheduler = ActuationScheduler(
        can_writer=_CountingWriter(),
        mailbox=mailbox,
        clock=clock,
        lease=LeaseManager(LEASE_DURATION_SEC),
        initial_producer=MailboxProducer("p", mailbox, clock),
        initial_hold_positions=tuple(Rad(0.0) for _ in range(MIT_BATCH_WIDTH)),
        trace=TickTrace(),
    )
    ring = AuditRingBuffer(on_integrity_fault=scheduler.engage_safety_latch)
    result, request = _clean_decision()
    chain = _corrupt(clean_chain(result.accepted), 0, offset_applications=1)

    with pytest.raises(OffsetIntegrityError):
        ring.record(record_from(result, request, tick_index=0, at=0.0, chain=chain))

    assert scheduler.latch_active
    emission = scheduler.tick()
    assert emission.label is EmissionLabel.SAFETY_LATCH_HOLD


def test_check_chain_is_clean_when_the_offset_is_applied_exactly_once() -> None:
    """The integrity primitive passes an option-(b) chain that applied the offset once (②)."""
    result, _request = _clean_decision()
    chain = clean_chain(result.accepted, offset_rad=OPTION_B_OFFSET_RAD, applications=1)

    verdict = check_chain(chain, expected_applications=1)

    assert verdict.ok
    assert verdict.joint_index is None


class _CountingWriter:
    """A CAN-free writer that counts one send per batch — the scheduler's invariant needs it."""

    def __init__(self) -> None:
        """Start the send count at zero."""
        self._count = 0

    @property
    def write_count(self) -> int:
        """Cumulative successful sends.

        Returns:
            (int) Number of batches sent.
        """
        return self._count

    def mit_control_batch(self, batch: tuple[ExecutedMitCommand, ...]) -> None:
        """Count one send.

        Args:
            batch: The batch the scheduler asked to send.
        """
        self._count += 1
