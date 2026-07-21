"""Check ① — joint position limit (`09` FR-SIM-030 ①).

Compares each arm joint's ``qpos`` against a position bound and reports every
joint outside it as one ``OA-DRY-001`` violation, with the overage in radians.

The bound source is a *selected* canon, not a hard-coded table: `09` FR-SIM-031
lists three real candidates (URDF / MJCF / LeRobot) and refuses to run until one
is chosen. This module takes the resolved per-joint bounds as an argument — the
canon resolution and the refuse-if-unselected gate live in ``canon.py`` — so this
file only applies bounds, never decides which are canon.
"""

from __future__ import annotations

from collections.abc import Mapping

import mujoco

from sim.dryrun.topology import arm_joint_addresses
from sim.dryrun.violation import DryRunCheck, Violation

# A qpos within this many radians of a bound is treated as inside it; only travel
# strictly past the bound by more than this numerical margin is a violation.
POSITION_TOLERANCE_RAD = 1e-9


def check_position_limits(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    bounds_rad: Mapping[str, tuple[float, float]],
    sim_t: float,
) -> tuple[Violation, ...]:
    """Report every arm joint whose position is outside its selected bound.

    Args:
        model: The compiled model.
        data: The model state whose ``qpos`` is judged.
        bounds_rad: Motor key to ``(lower_rad, upper_rad)`` from the selected canon.
        sim_t: Simulation time in seconds, stamped onto each violation.

    Returns:
        (tuple[Violation, ...]) One ``OA-DRY-001`` per out-of-bound joint.
    """
    violations: list[Violation] = []
    for address in arm_joint_addresses(model):
        bound = bounds_rad.get(address.motor_key)
        if bound is None:
            continue
        lower, upper = bound
        position = float(data.qpos[address.qpos_adr])
        if position < lower - POSITION_TOLERANCE_RAD:
            violations.append(_violation(address.motor_key, sim_t, lower - position))
        elif position > upper + POSITION_TOLERANCE_RAD:
            violations.append(_violation(address.motor_key, sim_t, position - upper))
    return tuple(violations)


def _violation(motor_key: str, sim_t: float, overage_rad: float) -> Violation:
    """Build one position-limit violation."""
    return Violation(
        item=DryRunCheck.POSITION_LIMIT,
        sim_t=sim_t,
        joint=motor_key,
        overage=overage_rad,
    )
