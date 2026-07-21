"""WP-0A-01 — the ActuationScheduler, the runtime spine and single CAN writer.

The one loop through which every command to the arm passes. This package owns the
scheduler, its publish-only mailbox, the four-emission decider, the atomic
producer swap, the deadman lease, the safety latch, the tick trace, and the
fault-injection harness (a fake CAN backend and a controlled clock) that proves
the whole thing `AI-offline`.

Public surface: consumers import the scheduler and its collaborators from here.
Producers are given a `TargetMailbox` and never anything from `can_writer` — the
single-CAN-writer invariant (`02a` §3.1 ①) is enforced both structurally (no path
from a mailbox to a CAN handle) and statically (`staticcheck.find_producer_can_access`).
"""

from __future__ import annotations

from backend.actuation.can_writer import (
    MIT_BATCH_WIDTH,
    CanBusFaultError,
    CanWriter,
    FakeCanWriter,
)
from backend.actuation.clock import Clock, ManualClock
from backend.actuation.decider import DeciderInput, decide
from backend.actuation.emissions import (
    HOLD_LABELS,
    Emission,
    EmissionLabel,
    ReasonCode,
)
from backend.actuation.gateway import (
    JointLimit,
    accepted_to_rad,
    clamp_request,
    positions_to_batch,
)
from backend.actuation.harness import FaultInjectionHarness
from backend.actuation.latch import SafetyLatch
from backend.actuation.lease import LeaseManager
from backend.actuation.mailbox import TargetMailbox, TimestampedTarget
from backend.actuation.producer import MailboxProducer, Producer
from backend.actuation.scheduler import ActuationScheduler, EmissionInvariantError
from backend.actuation.staticcheck import (
    StaticViolation,
    find_disable_torque,
    find_producer_can_access,
)
from backend.actuation.trace import TallyTrace, TickRecord, TickTrace, TraceSink
from backend.actuation.transition import ModeTransition

__all__ = [
    "HOLD_LABELS",
    "MIT_BATCH_WIDTH",
    "ActuationScheduler",
    "CanBusFaultError",
    "CanWriter",
    "Clock",
    "DeciderInput",
    "Emission",
    "EmissionInvariantError",
    "EmissionLabel",
    "FakeCanWriter",
    "FaultInjectionHarness",
    "JointLimit",
    "LeaseManager",
    "MailboxProducer",
    "ManualClock",
    "ModeTransition",
    "Producer",
    "ReasonCode",
    "SafetyLatch",
    "StaticViolation",
    "TallyTrace",
    "TargetMailbox",
    "TickRecord",
    "TickTrace",
    "TimestampedTarget",
    "TraceSink",
    "accepted_to_rad",
    "clamp_request",
    "decide",
    "find_disable_torque",
    "find_producer_can_access",
    "positions_to_batch",
]
