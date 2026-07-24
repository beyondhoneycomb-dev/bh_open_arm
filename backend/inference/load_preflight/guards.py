"""Command wrap (PMAX) and the velocity-limit / jump-guard separation (FR-INF-038/039/040).

Two action-layer guards this band must get right, both sourced from the committed
motor tables rather than fresh constants:

- Wrap (FR-INF-038): a commanded position beyond +/-PMAX must be refused, not wrapped.
  Every Damiao motor encodes position over +/-12.5 rad (`MOTOR_LIMIT_PARAMS[*].p_max`),
  so a command past it does not saturate — the 12-bit field wraps to the opposite end,
  which is a large silent jump. `command_within_pmax` refuses instead.

- Velocity vs jump guard (FR-INF-040): these are SEPARATE parameters and neither
  substitutes for the other. The velocity limit is `|dq|/dt` per joint, capped at
  `min(user, motor VMAX)` (FR-INF-039; `MOTOR_LIMIT_PARAMS[*].v_max` — DM8009 45,
  DM4340 8, DM4310 30 rad/s). The jump guard is LeRobot's `max_relative_target`, a
  per-step `|dq|` cap that at 50 Hz says nothing about velocity (1.8 rad/step is 90
  rad/s). `MotionGuards` holds them as two fields so one can never be read as the other.

The per-index motor family is the committed `ARM_JOINT_MOTORS` (seven arm joints) plus
the DM4310 gripper (LeRobot `motor_config`), so the VMAX/PMAX a joint is checked
against is the family actually driving it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from backend.can.rid.motor_limits import MOTOR_LIMIT_PARAMS, MotorType
from backend.safety_bringup.constants import ARM_JOINT_MOTORS

# The gripper (finger) motor is a DM4310 per LeRobot `motor_config`; it is not one of
# the seven arm joints `ARM_JOINT_MOTORS` covers, so it is appended explicitly.
GRIPPER_MOTOR = MotorType.DM4310

# One arm's eight driver motors, in MOTOR_ORDER: seven arm joints then the gripper.
JOINT_MOTORS: tuple[MotorType, ...] = (*ARM_JOINT_MOTORS, GRIPPER_MOTOR)

# Both arms' sixteen driver motors, right then left, matching the bimanual layout.
BIMANUAL_JOINT_MOTORS: tuple[MotorType, ...] = JOINT_MOTORS + JOINT_MOTORS


def pmax_rad(motor: MotorType) -> float:
    """Return a motor's CAN position-scale limit PMAX (rad) — the wrap boundary."""
    return MOTOR_LIMIT_PARAMS[motor].p_max


def motor_vmax_rad_s(motor: MotorType) -> float:
    """Return a motor's velocity-scale limit VMAX (rad/s) — the FR-INF-039 ceiling."""
    return MOTOR_LIMIT_PARAMS[motor].v_max


def _motors_for(length: int) -> tuple[MotorType, ...]:
    """Return the driver-motor tuple matching a command/limit vector length.

    Args:
        length: 8 for a single arm, 16 for bimanual.

    Returns:
        (tuple[MotorType, ...]) The per-index motor families.

    Raises:
        ValueError: When `length` is neither the single-arm nor bimanual width.
    """
    if length == len(JOINT_MOTORS):
        return JOINT_MOTORS
    if length == len(BIMANUAL_JOINT_MOTORS):
        return BIMANUAL_JOINT_MOTORS
    raise ValueError(
        f"command/limit vector must be {len(JOINT_MOTORS)} (single) or "
        f"{len(BIMANUAL_JOINT_MOTORS)} (bimanual) wide, got {length}"
    )


@dataclass(frozen=True)
class CommandWrapVerdict:
    """The result of one command-vs-PMAX check.

    Attributes:
        ok: True when every commanded position is within its motor's +/-PMAX.
        offenders: `(index, value_rad, pmax_rad)` for each joint that overran; empty
            when `ok`.
    """

    ok: bool
    offenders: tuple[tuple[int, float, float], ...]

    def detail(self) -> str:
        """Return the operator-facing sentence for a wrap refusal."""
        parts = ", ".join(
            f"j{index}={value:.3f} rad exceeds +/-{limit} rad"
            for index, value, limit in self.offenders
        )
        return f"commanded position exceeds PMAX and would wrap (FR-INF-038): {parts}"


def command_within_pmax(
    command_rad: Sequence[float],
    motors: Sequence[MotorType] | None = None,
) -> CommandWrapVerdict:
    """Check that every commanded position is within its motor's +/-PMAX (FR-INF-038).

    Args:
        command_rad: The commanded joint positions (radians), 8 or 16 wide.
        motors: The per-index motor families; derived from the command width when None.

    Returns:
        (CommandWrapVerdict) Whether the command is in range, and any offenders.
    """
    resolved_motors = tuple(motors) if motors is not None else _motors_for(len(command_rad))
    offenders: list[tuple[int, float, float]] = []
    for index, value in enumerate(command_rad):
        limit = pmax_rad(resolved_motors[index])
        if abs(value) > limit:
            offenders.append((index, float(value), limit))
    return CommandWrapVerdict(ok=not offenders, offenders=tuple(offenders))


def resolve_velocity_limit(
    user_limit_rad_s: Sequence[float],
    motors: Sequence[MotorType] | None = None,
) -> tuple[float, ...]:
    """Resolve the per-joint velocity ceiling = `min(user, motor VMAX)` (FR-INF-039).

    Args:
        user_limit_rad_s: The user-requested per-joint velocity ceiling (rad/s).
        motors: The per-index motor families; derived from the vector width when None.

    Returns:
        (tuple[float, ...]) The effective per-joint velocity ceiling (rad/s), never
            above the motor's VMAX.
    """
    resolved_motors = tuple(motors) if motors is not None else _motors_for(len(user_limit_rad_s))
    return tuple(
        min(float(user), motor_vmax_rad_s(motor))
        for user, motor in zip(user_limit_rad_s, resolved_motors, strict=True)
    )


@dataclass(frozen=True)
class MotionGuards:
    """The two SEPARATE action-rate parameters (FR-INF-040): they never substitute.

    LeRobot exposes only `max_relative_target` (the jump guard) and has no velocity
    limit at all, so conflating the two would leave `|dq|/dt` unbounded. These are two
    fields on purpose.

    Attributes:
        velocity_limit_rad_s: Per-joint `|dq|/dt` ceiling (rad/s), the true velocity
            limit — resolve it with `resolve_velocity_limit` so it never exceeds VMAX.
        jump_guard: LeRobot's `max_relative_target` — a per-step `|dq|` cap (a scalar,
            a per-motor dict, or None when off). NOT a velocity limit.
    """

    velocity_limit_rad_s: tuple[float, ...]
    jump_guard: float | dict[str, float] | None

    def jump_guard_enabled(self) -> bool:
        """Report whether the jump guard is active (LeRobot default is off / None)."""
        return self.jump_guard is not None
