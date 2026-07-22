"""Assemble the position envelope the Move-to limit check runs against.

The Move-to limit check reuses WP-2A-03's ``JogClampPath``, which needs a validated
``SafetyLimits``. Its *mechanical* position bound must be the same one the IK adapter
clamps to — LeRobot's soft limits — or the EE-path limit check and the IK-existence
check would disagree about what "in bounds" means. So the mechanical envelope here is
read straight from ``sim.ik.all_soft_limits`` (the single upstream truth, FR-SYS-016),
never re-spelled.

Everything ``SafetyLimits.validate`` also requires — the operational subset, the three
rate guards, the torque pair — is a caller input, not an invented safety number. The
Move-to gate consumes only the *position* envelope; the rate and torque axes are
validated for consistency but enforced elsewhere (the send_action gateway), so this
module refuses to fabricate values for them and takes them explicitly instead. A
deployment with a canonical ``SafetyLimits`` already in hand should inject that directly
and skip this helper.
"""

from __future__ import annotations

from backend.actuation.safety import SafetyLimits
from backend.moveto.constants import BIMANUAL_WIDTH
from contracts.units import Deg, Nm
from sim.ik.limits import all_soft_limits


def soft_limit_mechanical_deg() -> tuple[tuple[Deg, Deg], ...]:
    """Return the 16-dim mechanical position envelope from the soft-limit truth.

    Reads ``sim.ik.all_soft_limits`` — the same source the IK adapter's jnt_range
    override uses — so the Move-to mechanical bound and the adapter's are one value,
    in the 16-dim right-then-left order the solution vector uses.

    Returns:
        (tuple[tuple[Deg, Deg], ...]) Per-slot ``(low, high)`` in degrees, 16 entries.
    """
    return tuple((limit.lower_deg, limit.upper_deg) for limit in all_soft_limits())


def _broadcast_float(value: float | tuple[float, ...], width: int, name: str) -> tuple[float, ...]:
    """Expand a scalar to ``width`` copies, or pass a correctly-sized tuple through.

    Args:
        value: A scalar applied to every joint, or a per-joint tuple.
        width: The command width the result must have.
        name: The field name, for the width-mismatch message.

    Returns:
        (tuple[float, ...]) The per-joint values, ``width`` wide.

    Raises:
        ValueError: When a tuple is given whose width does not match.
    """
    if isinstance(value, tuple):
        if len(value) != width:
            raise ValueError(f"{name} must be {width}-wide, got {len(value)}")
        return value
    return (float(value),) * width


def _broadcast_torque(value: float | tuple[float, ...], width: int, name: str) -> tuple[Nm, ...]:
    """Expand a scalar torque to ``width`` copies, or wrap a per-joint tuple as ``Nm``.

    Args:
        value: A scalar torque applied to every joint, or a per-joint tuple.
        width: The command width the result must have.
        name: The field name, for the width-mismatch message.

    Returns:
        (tuple[Nm, ...]) The per-joint torque ceilings, ``width`` wide.

    Raises:
        ValueError: When a tuple is given whose width does not match.
    """
    return tuple(Nm(v) for v in _broadcast_float(value, width, name))


def move_to_limits_from_soft_limits(
    *,
    velocity_limit_rad_s: float | tuple[float, ...],
    accel_limit_rad_s2: float | tuple[float, ...],
    jerk_limit_rad_s3: float | tuple[float, ...],
    step_delta_limit_rad: float | tuple[float, ...],
    peak_torque_nm: float | tuple[float, ...],
    operational_torque_nm: float | tuple[float, ...],
    operational_deg: tuple[tuple[Deg, Deg], ...] | None = None,
) -> SafetyLimits:
    """Build a validated 16-dim ``SafetyLimits`` for the Move-to limit check.

    The mechanical position envelope comes from the soft-limit truth; the operational
    envelope defaults to the mechanical one (equal is a valid subset) unless a tighter
    one is supplied. The rate and torque axes are the caller's — the Move-to gate does
    not use them for the position check, but ``validate`` requires them present, so they
    are taken as inputs rather than invented.

    Args:
        velocity_limit_rad_s: Per-joint velocity ceiling, scalar or 16-tuple.
        accel_limit_rad_s2: Per-joint acceleration ceiling, scalar or 16-tuple.
        jerk_limit_rad_s3: Per-joint jerk ceiling, scalar or 16-tuple.
        step_delta_limit_rad: Per-joint step-delta jump guard, scalar or 16-tuple.
        peak_torque_nm: Per-joint physical peak torque, scalar or 16-tuple.
        operational_torque_nm: Per-joint operational torque ceiling, scalar or 16-tuple.
        operational_deg: A tighter operational position envelope; None reuses the
            mechanical one.

    Returns:
        (SafetyLimits) A validated envelope whose mechanical bound is the soft-limit
        truth.

    Raises:
        SafetyConfigError: When the assembled set fails ``SafetyLimits.validate``.
    """
    mechanical_deg = soft_limit_mechanical_deg()
    limits = SafetyLimits(
        mechanical_deg=mechanical_deg,
        operational_deg=operational_deg if operational_deg is not None else mechanical_deg,
        velocity_limit_rad_s=_broadcast_float(
            velocity_limit_rad_s, BIMANUAL_WIDTH, "velocity_limit_rad_s"
        ),
        accel_limit_rad_s2=_broadcast_float(
            accel_limit_rad_s2, BIMANUAL_WIDTH, "accel_limit_rad_s2"
        ),
        jerk_limit_rad_s3=_broadcast_float(jerk_limit_rad_s3, BIMANUAL_WIDTH, "jerk_limit_rad_s3"),
        step_delta_limit_rad=_broadcast_float(
            step_delta_limit_rad, BIMANUAL_WIDTH, "step_delta_limit_rad"
        ),
        peak_torque_nm=_broadcast_torque(peak_torque_nm, BIMANUAL_WIDTH, "peak_torque_nm"),
        operational_torque_nm=_broadcast_torque(
            operational_torque_nm, BIMANUAL_WIDTH, "operational_torque_nm"
        ),
    )
    limits.validate()
    return limits
