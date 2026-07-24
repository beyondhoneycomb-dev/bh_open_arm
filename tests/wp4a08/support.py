"""Builders that ground the WP-4A-08 gates on the committed spine, not on mocks.

`THE ONE RULE` for this band holds here: the detector publishes into the committed
`FaultInjectionHarness` mailbox that the real `ActuationScheduler` reads, and it reads
the committed `QueueMeter` (WP-4A-07) for the starvation ratio. The only stand-ins are
the *injected faults* the acceptance gates pull — a runaway signal, a NaN action, a
disconnect health snapshot — never a substitute for the upstream that must react.

The thresholds used here are `metering_placeholder_thresholds()`: un-validated
placeholders (SPINE §2-6, values are 4C's), chosen so a healthy stream stays under and
an injected fault goes over. They are not production limits and the factory says so.
"""

from __future__ import annotations

from collections.abc import Sequence

from backend.actuation import FaultInjectionHarness, JointLimit, MailboxProducer
from backend.inference.adapter import QueueMeter
from backend.inference.runaway import (
    RemoteHealth,
    RunawayDetector,
    RunawayThresholds,
    metering_placeholder_thresholds,
)
from contracts.action import BIMANUAL_ACTION_DIM, RequestedPositionAction
from contracts.units import Deg

# A neutral in-range hold pose the detector holds at before any valid action (`qh`).
NEUTRAL_HOLD = RequestedPositionAction(values=tuple(Deg(0.0) for _ in range(BIMANUAL_ACTION_DIM)))


def flat_vector(value: float) -> list[float]:
    """Return a `BIMANUAL_ACTION_DIM`-wide vector with every joint at `value`.

    Args:
        value: The per-joint position in degrees.

    Returns:
        (list[float]) The 16-wide vector.
    """
    return [value for _ in range(BIMANUAL_ACTION_DIM)]


def tight_limits(low: float = -1.0, high: float = 1.0) -> tuple[JointLimit, ...]:
    """Return a symmetric per-joint limit that clamps every joint tightly.

    Args:
        low: Lower bound in degrees.
        high: Upper bound in degrees.

    Returns:
        (tuple[JointLimit, ...]) One `(low, high)` bound per joint.
    """
    return tuple((Deg(low), Deg(high)) for _ in range(BIMANUAL_ACTION_DIM))


def single_joint_limit(joint: int, low: float, high: float) -> tuple[JointLimit | None, ...]:
    """Return limits that clamp exactly one joint and leave the rest unclamped.

    Args:
        joint: The joint index to clamp.
        low: Lower bound in degrees for that joint.
        high: Upper bound in degrees for that joint.

    Returns:
        (tuple[JointLimit | None, ...]) Per-joint limits, None on every other joint.
    """
    return tuple(
        (Deg(low), Deg(high)) if index == joint else None for index in range(BIMANUAL_ACTION_DIM)
    )


def make_detector(
    harness: FaultInjectionHarness,
    thresholds: RunawayThresholds | None = None,
    meter: QueueMeter | None = None,
    joint_limits: tuple[JointLimit | None, ...] | None = None,
) -> RunawayDetector:
    """Build a detector publishing into the committed harness mailbox.

    Args:
        harness: The committed fault-injection harness (real scheduler + mailbox).
        thresholds: The four thresholds; metering placeholders when omitted.
        meter: The committed queue meter; a fresh one when omitted.
        joint_limits: The scheduler's per-joint limits, shared so the logged accepted
            action equals the sent one.

    Returns:
        (RunawayDetector) A detector wired to the harness mailbox and clock.
    """
    producer = MailboxProducer("runaway-detector", harness.mailbox, harness.clock)
    return RunawayDetector(
        producer=producer,
        meter=meter if meter is not None else QueueMeter(),
        thresholds=thresholds if thresholds is not None else metering_placeholder_thresholds(),
        initial_hold=NEUTRAL_HOLD,
        joint_limits=joint_limits,
    )


def drive_meter_starved(meter: QueueMeter, starved: int, served: int) -> None:
    """Drive the committed meter to a chosen exhaustion ratio.

    Args:
        meter: The queue meter to drive.
        starved: Number of starved ticks to record (queue size 0).
        served: Number of served ticks to record (queue size 1).
    """
    for _ in range(served):
        meter.tick(1)
    for _ in range(starved):
        meter.tick(0)


def healthy_remote(action: Sequence[float] | None = None) -> RemoteHealth:
    """Return a fully healthy remote-health snapshot, optionally with a returned action.

    Args:
        action: The action the server returned; a neutral vector when omitted.

    Returns:
        (RemoteHealth) A snapshot `classify_remote` reports as healthy.
    """
    return RemoteHealth(
        transport_ok=True,
        ready_ok=True,
        rpc_deadline_exceeded=False,
        session_epoch=1,
        expected_epoch=1,
        observation_wall_age_sec=0.0,
        max_wall_age_sec=2.0,
        action=action if action is not None else flat_vector(0.0),
        queue_wait_timed_out=False,
    )
