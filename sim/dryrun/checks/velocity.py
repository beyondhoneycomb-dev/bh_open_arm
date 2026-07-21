"""Check ② — joint velocity limit (`09` FR-SIM-030 ②).

Compares each arm joint's ``qvel`` magnitude against a per-joint velocity bound
(rad/s) and reports every joint over it as one ``OA-DRY-002`` violation, with the
overage in rad/s.

`09` FR-SIM-032 (§5 Q4) makes the velocity canon decision-required: three real
candidate tables exist and none is chosen. This module applies whichever table the
selected canon resolved to; it does not carry a default. The refusal to run
without a selected velocity canon lives in ``canon.py`` (`09` FR-SIM-132), so a
missing canon is a hard refusal upstream, never a silent zero-limit here.
"""

from __future__ import annotations

from collections.abc import Mapping

import mujoco

from sim.dryrun.topology import arm_joint_addresses
from sim.dryrun.violation import DryRunCheck, Violation

# A speed within this many rad/s of the bound counts as inside it (numerical noise).
VELOCITY_TOLERANCE_RAD_S = 1e-9


def check_velocity_limits(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    limits_rad_s: Mapping[str, float],
    sim_t: float,
) -> tuple[Violation, ...]:
    """Report every arm joint whose speed exceeds its selected velocity bound.

    Args:
        model: The compiled model.
        data: The model state whose ``qvel`` is judged.
        limits_rad_s: Motor key to symmetric speed bound (rad/s), selected canon.
        sim_t: Simulation time in seconds, stamped onto each violation.

    Returns:
        (tuple[Violation, ...]) One ``OA-DRY-002`` per over-speed joint.
    """
    violations: list[Violation] = []
    for address in arm_joint_addresses(model):
        limit = limits_rad_s.get(address.motor_key)
        if limit is None:
            continue
        speed = abs(float(data.qvel[address.dof_adr]))
        bound = abs(limit)
        if speed > bound + VELOCITY_TOLERANCE_RAD_S:
            violations.append(
                Violation(
                    item=DryRunCheck.VELOCITY_LIMIT,
                    sim_t=sim_t,
                    joint=address.motor_key,
                    overage=speed - bound,
                )
            )
    return tuple(violations)
