"""Check ⑥ — lifter stroke (`09` FR-SIM-030 ⑥).

Reports the prismatic lifter position leaving its ``[0, 0.3]`` metre stroke as one
``OA-DRY-006`` violation, the overage being metres past the nearer end. The bound
is the confirmed physical stroke of the lifter (matching the MJCF joint range and
the ``lifter_ctrl`` ``ctrlrange``), so unlike the position and velocity checks it
carries its own fixed limits rather than a selected canon.

Acceptance ⑧ pins the boundary: ``0`` and ``0.3`` are exactly on-stroke and pass;
travel beyond either end by more than a numerical margin is the violation.
"""

from __future__ import annotations

import mujoco

from sim.dryrun.topology import lifter_address
from sim.dryrun.violation import DryRunCheck, Violation

# The confirmed lifter stroke in metres (`09` FR-SIM-030 ⑥).
LIFTER_STROKE_MIN_M = 0.0
LIFTER_STROKE_MAX_M = 0.3

# A position within this many metres of an end counts as on-stroke (numerical noise
# and the exact boundary values 0 / 0.3 both pass).
LIFTER_TOLERANCE_M = 1e-9


def check_lifter_stroke(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    sim_t: float,
) -> tuple[Violation, ...]:
    """Report the lifter leaving its ``[0, 0.3]`` metre stroke.

    Args:
        model: The compiled model.
        data: The state whose lifter ``qpos`` is judged.
        sim_t: Simulation time in seconds, stamped onto the violation.

    Returns:
        (tuple[Violation, ...]) One ``OA-DRY-006`` if off-stroke, else empty.
    """
    address = lifter_address(model)
    position = float(data.qpos[address.qpos_adr])
    if position < LIFTER_STROKE_MIN_M - LIFTER_TOLERANCE_M:
        overage = LIFTER_STROKE_MIN_M - position
    elif position > LIFTER_STROKE_MAX_M + LIFTER_TOLERANCE_M:
        overage = position - LIFTER_STROKE_MAX_M
    else:
        return ()
    return (
        Violation(
            item=DryRunCheck.LIFTER_STROKE,
            sim_t=sim_t,
            joint=address.motor_key,
            overage=overage,
        ),
    )
