"""Check ③ — actuator torque limit (`09` FR-SIM-030 ③, FR-SIM-133).

Compares each arm joint's effort against its ``Nm`` limit (J1/J2 ±40, J3/J4
±27, J5-J7 ±7) and reports every joint over it as one ``OA-DRY-003`` violation,
the overage in newton-metres. Efforts and limits are ``Nm`` (CTR-UNIT@v1), so a
packet-scale value cannot reach the comparison — the type forbids it.

FR-SIM-133 is the trap this module exists to disarm. On an *implicit* actuator
(the MJCF position actuators) the reported actuator force ``qfrc_actuator`` is
already clipped to ``forcerange``, so it never exceeds the limit and a torque
check reading it *silently passes* — the check is inert. The honest effort source
is the joint's *required* torque, computed by inverse dynamics
(``measured_efforts_via_inverse`` → ``mj_inverse`` → ``qfrc_inverse``), the sim
analogue of ``get_measured_joint_efforts()``; it reveals the demand the clamp hid.
``inert_actuator_efforts`` exposes the trap deliberately, so a test can show the
naive path passing and the measured path catching the same over-torque.
"""

from __future__ import annotations

from collections.abc import Mapping

import mujoco

from contracts.units.tags import Nm
from sim.dryrun.topology import arm_joint_addresses
from sim.dryrun.violation import DryRunCheck, Violation

# An effort within this many Nm of the bound counts as inside it (numerical noise).
TORQUE_TOLERANCE_NM = 1e-9


def check_torque_limits(
    efforts_nm: Mapping[str, Nm],
    limits_nm: Mapping[str, Nm],
    sim_t: float,
) -> tuple[Violation, ...]:
    """Report every arm joint whose effort exceeds its ``Nm`` torque limit.

    The efforts must be a *measured/required* torque, not the clamped actuator
    force — see ``measured_efforts_via_inverse`` and the FR-SIM-133 note above.

    Args:
        efforts_nm: Motor key to the joint's effort in Nm.
        limits_nm: Motor key to its symmetric torque bound in Nm.
        sim_t: Simulation time in seconds, stamped onto each violation.

    Returns:
        (tuple[Violation, ...]) One ``OA-DRY-003`` per over-torque joint.
    """
    violations: list[Violation] = []
    for motor_key, limit in limits_nm.items():
        effort = efforts_nm.get(motor_key)
        if effort is None:
            continue
        magnitude = abs(effort.value)
        bound = abs(limit.value)
        if magnitude > bound + TORQUE_TOLERANCE_NM:
            violations.append(
                Violation(
                    item=DryRunCheck.TORQUE_LIMIT,
                    sim_t=sim_t,
                    joint=motor_key,
                    overage=magnitude - bound,
                )
            )
    return tuple(violations)


def measured_efforts_via_inverse(model: mujoco.MjModel, data: mujoco.MjData) -> dict[str, Nm]:
    """Return each arm joint's *required* torque (Nm) via inverse dynamics.

    This is the FR-SIM-133 honest source: ``mj_inverse`` solves for the
    generalised force that realises the current ``qpos``/``qvel``/``qacc``, giving
    the torque the joint truly demands — unclipped by any actuator ``forcerange``.
    It is the sim analogue of ``get_measured_joint_efforts()``.

    Args:
        model: The compiled model.
        data: The state to evaluate; its ``qacc`` is read as the target acceleration
            (set it to zero for a quasi-static holding-torque check).

    Returns:
        (dict[str, Nm]) Motor key to required joint torque in Nm.
    """
    mujoco.mj_inverse(model, data)
    return {
        address.motor_key: Nm(float(data.qfrc_inverse[address.dof_adr]))
        for address in arm_joint_addresses(model)
    }


def inert_actuator_efforts(model: mujoco.MjModel, data: mujoco.MjData) -> dict[str, Nm]:
    """Return each arm joint's *clamped actuator* force (Nm) — the inert source.

    Exists only to demonstrate FR-SIM-133: on an implicit actuator this value is
    already clipped to ``forcerange``, so a torque check reading it can never see
    an over-torque. A dry-run must never use this as its effort source; a test uses
    it to prove the naive path is inert against a case the measured path catches.

    Args:
        model: The compiled model.
        data: The forward-evaluated state (call ``mj_forward`` first).

    Returns:
        (dict[str, Nm]) Motor key to clamped actuator force in Nm.
    """
    return {
        address.motor_key: Nm(float(data.qfrc_actuator[address.dof_adr]))
        for address in arm_joint_addresses(model)
    }
