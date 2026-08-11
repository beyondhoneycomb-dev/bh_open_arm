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
What fills that mailbox is `AcceptedTargetPublisher`, which takes a gateway decision and
nothing else, so the frame the single writer emits is one the eight-check filter passed.
"""

from __future__ import annotations

from backend.actuation.assembly import AcceptedTargetPublisher
from backend.actuation.bus_writer import (
    ANSWERED_STATE_FIELDS,
    BIMANUAL_BATCH_WIDTH,
    ArmWriteSlots,
    BimanualCanWriter,
    BusCanWriter,
    DropCounter,
    MitBus,
    bus_command_tuple,
    is_cache_initialiser,
)
from backend.actuation.can_writer import (
    MIT_BATCH_WIDTH,
    CanBusFaultError,
    CanWriter,
    FakeCanWriter,
)
from backend.actuation.clock import Clock, ManualClock, WallClock
from backend.actuation.decider import DeciderInput, decide
from backend.actuation.emissions import (
    HOLD_LABELS,
    Emission,
    EmissionLabel,
    ReasonCode,
)
from backend.actuation.enforcement import (
    ActuationGateway,
    GateFrame,
    GateResult,
)
from backend.actuation.errdecode import (
    DecodedMotorErr,
    UnknownErrNibbleError,
    decode_motor_err,
)
from backend.actuation.gains import (
    CALIB_HOLD,
    COMPLIANT,
    GAIN_PROFILES,
    LEROBOT_FOLLOWER,
    LEROBOT_RUNTIME_PROFILE,
    ROS2_CONTROL_GRIPPER_KD,
    ROS2_CONTROL_GRIPPER_KP,
    STIFF,
    TELEOP_FOLLOWER,
    GainLineage,
    GainProfileError,
    JointGains,
    NamedGainProfile,
    UnknownGainProfileError,
    profile_names,
    resolve_gain_profile,
)
from backend.actuation.gateway import (
    JointLimit,
    accepted_to_rad,
    clamp_request,
    positions_to_batch,
)
from backend.actuation.guard import (
    CollisionGuard,
    GuardCause,
    GuardSample,
    GuardVerdict,
)
from backend.actuation.harness import FaultInjectionHarness
from backend.actuation.latch import SafetyLatch
from backend.actuation.lease import LeaseManager
from backend.actuation.mailbox import TargetMailbox, TimestampedTarget
from backend.actuation.producer import MailboxProducer, Producer
from backend.actuation.safety import (
    CHECK_ORDER,
    CheckStage,
    FilterInput,
    FilterOutcome,
    MotionHistory,
    SafetyConfigError,
    SafetyFilter,
    SafetyLimits,
    SafetyReason,
    clamp_reason_for,
)
from backend.actuation.scheduler import ActuationScheduler, EmissionInvariantError
from backend.actuation.staticcheck import (
    StaticViolation,
    find_disable_torque,
    find_producer_can_access,
)
from backend.actuation.trace import TallyTrace, TickRecord, TickTrace, TraceSink
from backend.actuation.transition import ModeTransition
from backend.actuation.watchdog import FIRST_COMMAND_GAP_SEC, ActionStreamWatchdog

__all__ = [
    "ANSWERED_STATE_FIELDS",
    "BIMANUAL_BATCH_WIDTH",
    "CALIB_HOLD",
    "CHECK_ORDER",
    "COMPLIANT",
    "FIRST_COMMAND_GAP_SEC",
    "GAIN_PROFILES",
    "HOLD_LABELS",
    "LEROBOT_FOLLOWER",
    "LEROBOT_RUNTIME_PROFILE",
    "MIT_BATCH_WIDTH",
    "ROS2_CONTROL_GRIPPER_KD",
    "ROS2_CONTROL_GRIPPER_KP",
    "STIFF",
    "TELEOP_FOLLOWER",
    "AcceptedTargetPublisher",
    "ActionStreamWatchdog",
    "ActuationGateway",
    "ActuationScheduler",
    "ArmWriteSlots",
    "BimanualCanWriter",
    "BusCanWriter",
    "CanBusFaultError",
    "CanWriter",
    "CheckStage",
    "Clock",
    "CollisionGuard",
    "DecodedMotorErr",
    "DeciderInput",
    "DropCounter",
    "Emission",
    "EmissionInvariantError",
    "EmissionLabel",
    "FakeCanWriter",
    "FaultInjectionHarness",
    "FilterInput",
    "FilterOutcome",
    "GainLineage",
    "GainProfileError",
    "GateFrame",
    "GateResult",
    "GuardCause",
    "GuardSample",
    "GuardVerdict",
    "JointGains",
    "JointLimit",
    "LeaseManager",
    "MailboxProducer",
    "ManualClock",
    "MitBus",
    "ModeTransition",
    "MotionHistory",
    "NamedGainProfile",
    "Producer",
    "ReasonCode",
    "SafetyConfigError",
    "SafetyFilter",
    "SafetyLatch",
    "SafetyLimits",
    "SafetyReason",
    "StaticViolation",
    "TallyTrace",
    "TargetMailbox",
    "TickRecord",
    "TickTrace",
    "TimestampedTarget",
    "TraceSink",
    "UnknownErrNibbleError",
    "UnknownGainProfileError",
    "WallClock",
    "accepted_to_rad",
    "bus_command_tuple",
    "clamp_reason_for",
    "clamp_request",
    "decide",
    "decode_motor_err",
    "find_disable_torque",
    "find_producer_can_access",
    "is_cache_initialiser",
    "positions_to_batch",
    "profile_names",
    "resolve_gain_profile",
]
