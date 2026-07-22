"""Shared builders for WP-2A-05: a real Wave-1 gateway, and transform-chain factories.

The audit ring is exercised against the genuine Wave-1 clamp path — a real
`ActuationGateway` over a loose limit set, so exactly the joint-limit clamp fires and
`requested` and `accepted` genuinely differ — and against transform chains built either
consistent (offset applied the declared number of times) or deliberately corrupted, so
the offset double-add / miss block is proven on injected faults, not asserted.
"""

from __future__ import annotations

from collections.abc import Callable

from backend.actuation import (
    ActuationGateway,
    CollisionGuard,
    GateResult,
    ManualClock,
    SafetyFilter,
    SafetyLimits,
    accepted_to_rad,
    positions_to_batch,
)
from backend.audit import AuditRecord, JointTransform
from contracts.action import AcceptedPositionAction, ExecutedMitCommand
from contracts.units import Deg, Nm, Rad, deg_to_rad
from ops.cancel.scheduler import LatchReason

# The bimanual action width the CTR-ACT position channels index (`10` §2.3).
WIDTH = 16

# A control period and freshness window loose enough that only the position clamp is
# decisive in the acceptance-① scenario.
TEST_DT_SEC = 0.02
TEST_FRESHNESS_SEC = 0.05


def make_limits(
    *,
    mechanical_deg: float = 180.0,
    operational_deg: float = 90.0,
) -> SafetyLimits:
    """Build a 16-joint limit set, loose on every rate guard so the clamp is the only knob.

    Args:
        mechanical_deg: Symmetric mechanical position bound.
        operational_deg: Symmetric operational bound (a subset of mechanical).

    Returns:
        (SafetyLimits) The limit set.
    """
    return SafetyLimits(
        mechanical_deg=tuple((Deg(-mechanical_deg), Deg(mechanical_deg)) for _ in range(WIDTH)),
        operational_deg=tuple((Deg(-operational_deg), Deg(operational_deg)) for _ in range(WIDTH)),
        velocity_limit_rad_s=tuple(1.0e6 for _ in range(WIDTH)),
        accel_limit_rad_s2=tuple(1.0e9 for _ in range(WIDTH)),
        jerk_limit_rad_s3=tuple(1.0e12 for _ in range(WIDTH)),
        step_delta_limit_rad=tuple(1.0e3 for _ in range(WIDTH)),
        peak_torque_nm=tuple(Nm(40.0) for _ in range(WIDTH)),
        operational_torque_nm=tuple(Nm(40.0) for _ in range(WIDTH)),
    )


def make_gateway(
    on_latch: Callable[[LatchReason], None] | None = None,
) -> tuple[ActuationGateway, CollisionGuard]:
    """Build a real Wave-1 gateway and its collision guard over a manual clock.

    Args:
        on_latch: Optional latch callback for the guard; a no-op recorder otherwise.

    Returns:
        (tuple[ActuationGateway, CollisionGuard]) The gateway and its guard.
    """
    guard = CollisionGuard(on_latch=on_latch or _ignore_latch, clock=ManualClock())
    gateway = ActuationGateway(
        SafetyFilter(make_limits()),
        guard,
        dt_sec=TEST_DT_SEC,
        freshness_window_sec=TEST_FRESHNESS_SEC,
    )
    return gateway, guard


def _ignore_latch(_reason: LatchReason) -> None:
    """A latch callback that records nothing — the default when a test does not wire one."""


def filled(value: float) -> tuple[Deg, ...]:
    """Build a 16-joint degree vector with every joint at the same angle.

    Args:
        value: The angle every joint takes, degrees.

    Returns:
        (tuple[Deg, ...]) The degree vector.
    """
    return tuple(Deg(value) for _ in range(WIDTH))


def executed_from(accepted: tuple[Deg, ...]) -> tuple[ExecutedMitCommand, ...]:
    """Build the MIT batch the scheduler would emit for an accepted action (Wave-1 path).

    Args:
        accepted: The post-clamp accepted action, degrees.

    Returns:
        (tuple[ExecutedMitCommand, ...]) The position-only MIT batch.
    """
    return positions_to_batch(accepted_to_rad(AcceptedPositionAction(values=accepted)))


def clean_chain(
    accepted: tuple[Deg, ...],
    *,
    offset_rad: float = 0.0,
    applications: int = 0,
) -> tuple[JointTransform, ...]:
    """Build a transform chain where the offset was applied exactly `applications` times.

    `q_motor = q_user + applications · offset` on every joint, so the chain is consistent
    with the declared application count and passes the integrity check when the ring's
    expected count matches.

    Args:
        accepted: The accepted action the chain derives its user angles from, degrees.
        offset_rad: The declared per-joint offset (zero under convention a).
        applications: How many times the offset was applied.

    Returns:
        (tuple[JointTransform, ...]) One consistent transform per joint.
    """
    chain: list[JointTransform] = []
    for angle in accepted:
        q_user = deg_to_rad(angle)
        q_motor = Rad(q_user.value + applications * offset_rad)
        chain.append(
            JointTransform(
                q_user_rad=q_user,
                joint_offset_rad=Rad(offset_rad),
                q_motor_rad=q_motor,
                q_uint=_stand_in_uint(q_motor),
                offset_applications=applications,
            )
        )
    return tuple(chain)


def _stand_in_uint(q_motor: Rad) -> int:
    """A deterministic stand-in for the 16-bit MIT value the CAN layer would emit.

    The audit records whatever `q_uint` the wire actually carried; these tests do not
    exercise the CAN encoder (owned elsewhere), so a fixed monotone map stands in.

    Args:
        q_motor: The motor-frame command angle, radians.

    Returns:
        (int) A 16-bit stand-in value.
    """
    return int(round(q_motor.value * 1000.0)) & 0xFFFF


def record_from(
    result: GateResult,
    requested: tuple[Deg, ...],
    *,
    tick_index: int,
    at: float,
    chain: tuple[JointTransform, ...] | None = None,
) -> AuditRecord:
    """Assemble an `AuditRecord` from a real gateway decision and a transform chain.

    Args:
        result: The gateway's decision.
        requested: The pre-clamp request the decision was made from.
        tick_index: Monotonic tick number.
        at: Monotonic clock reading, seconds.
        chain: The transform chain; a clean, offset-free chain when None.

    Returns:
        (AuditRecord) The composed record.
    """
    return AuditRecord.from_decision(
        tick_index=tick_index,
        at=at,
        requested=requested,
        result=result,
        executed=executed_from(result.accepted),
        chain=chain if chain is not None else clean_chain(result.accepted),
    )
