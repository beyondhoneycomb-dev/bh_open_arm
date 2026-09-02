"""Turn the arm state boards into one `telemetry` body.

Pure: it takes the views a caller already read and returns a dict. Nothing here touches a socket,
a clock or a board, so every branch — a board that never published, an arm with no thermometer, a
stale reading — is drivable without a rig.

**Two consumers, one frame.** `S-03` reads per-motor diagnostics and the policy path reads the
frozen 48-channel observation vector. Both were written against this frame before it carried
anything. Both are on the board, because the bus answers five channels in the one refresh the
pose arrives in, so serving one and not the other would be a choice with nothing behind it.

**What absence looks like here is deliberate.** A board that has published nothing contributes no
arm entry rather than an entry of zeros; an arm whose reader has no thermometer contributes no
motor rows rather than rows reading 0 °C. Both are the same rule: this frame never carries a
number that a screen would render identically to a measurement when no measurement was taken.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from backend.actuation.board import ArmStateView
from backend.jog.config import NEAR_LIMIT_MARGIN_DEG
from backend.jog.proximity import evaluate_proximity
from contracts.plugin.robot_abc import raw_observation_channels
from contracts.units import deg_per_sec_to_rad_per_sec, deg_to_rad
from contracts.ws import (
    TELEMETRY_ARMS_FIELD,
    TELEMETRY_JOINTS_FIELD,
    TELEMETRY_MOTOR_STATES_FIELD,
    TELEMETRY_OBSERVATION_FIELD,
    TELEMETRY_SEQUENCE_FIELD,
)
from sim.ik.limits import soft_limits

# The key the 48-channel vector travels under, matching what LeRobot names it. An object rather
# than a bare list so a later observation key is an added key, not a reshaped frame.
OBSERVATION_STATE_KEY = "observation.state"

# The channel suffixes `raw_observation_channels` declares, mapped to the `ArmState` tuple each
# is read from. Declared here rather than derived, because the mapping is the one fact this
# module knows that neither side states: the frozen channel list says `.vel` and the board says
# `velocity_deg_s`, and nothing else crosses those two names.
_CHANNEL_SOURCES = {
    "pos": "joint_deg",
    "vel": "velocity_deg_s",
    "torque": "torque_nm",
}

# Row keys `S-03/motorDomain.ts` reads. It also reads `err_nibble`, which is NOT emitted: the
# vendor bus drops `data[0]`'s ERR bits before `sync_read_all_states` returns, so this process
# has never seen one. The screen already treats a missing nibble as disabled, and inventing a
# value would make an unread field look read.
MOTOR_ROW_JOINT_NAME = "joint_name"
MOTOR_ROW_TEMP_MOS = "temp_mos_c"
MOTOR_ROW_TEMP_ROTOR = "temp_rotor_c"

# Per-side liveness keys. The age is what separates a board that stopped advancing from an arm
# that is holding still — every reading in those two cases is identical. `stale` is that age
# already judged, because the deadline is derived from the control tick rate and this process is
# the only one that knows it: a browser given the age alone would have to invent the rate.
ARM_READ_AGE = "read_age_s"
ARM_STALE = "stale"
ARM_OBSERVATION_PRESENT = "observation_present"
ARM_BUS_READ_OK = "bus_read_ok"
ARM_LOCK_ACQUIRED = "lock_acquired"
ARM_RESIDUAL_EXCEEDED = "residual_exceeded"
ARM_TICK_INDEX = "tick_index"

# Joint row keys, read by `S-04`'s joint table and by the viewport's snapshot gate. Two names
# per row on purpose: `JOINT_ROW_NAME` is the URDF/MJCF joint the model and the limits are
# written against, `JOINT_ROW_MOTOR` is the LeRobot channel prefix the motor rows and the
# observation vector use. The crossing between those namespaces is a fact this process holds and
# neither consumer can derive, so it travels rather than being reconstructed by string surgery
# in a browser.
JOINT_ROW_NAME = "name"
JOINT_ROW_MOTOR = "motor"
JOINT_ROW_POSITION_DEG = "position_deg"
JOINT_ROW_POSITION_RAD = "position_rad"
JOINT_ROW_VELOCITY_DEG_S = "velocity_deg_s"
JOINT_ROW_VELOCITY_RAD_S = "velocity_rad_s"
JOINT_ROW_TORQUE_NM = "torque_nm"
JOINT_ROW_LIMIT_LOWER_DEG = "limit_lower_deg"
JOINT_ROW_LIMIT_UPPER_DEG = "limit_upper_deg"
JOINT_ROW_LIMIT_LOWER_RAD = "limit_lower_rad"
JOINT_ROW_LIMIT_UPPER_RAD = "limit_upper_rad"
JOINT_ROW_NEAR_LIMIT = "near_limit"
JOINT_ROW_BLOCKED_DIRECTION = "blocked_direction"


def _motor_names(side: str) -> list[str]:
    """The motor names of one side, in the frozen channel declaration's order."""
    seen: list[str] = []
    for channel in raw_observation_channels(bimanual=True):
        motor = channel.name.rsplit(".", maxsplit=1)[0]
        if motor.startswith(f"{side}_") and motor not in seen:
            seen.append(motor)
    return seen


def observation_vector(views: Mapping[str, ArmStateView]) -> list[float]:
    """The frozen 48-channel observation vector, in `raw_observation_channels` order.

    A channel whose side has published nothing reads 0.0, which is the only value a vector of
    fixed width can carry for it. That absence is recoverable from `arms`: a side missing there
    published nothing, and a consumer that reads the vector without checking is reading zeros it
    was told about.

    Args:
        views: One view per arm side, keyed as the boards are.

    Returns:
        (list[float]) One float per declared channel, in declaration order.
    """
    vector: list[float] = []
    for channel in raw_observation_channels(bimanual=True):
        motor, suffix = channel.name.rsplit(".", maxsplit=1)
        side = motor.split("_", maxsplit=1)[0]
        view = views.get(side)
        state = None if view is None else view.state
        if state is None:
            vector.append(0.0)
            continue
        readings = getattr(state, _CHANNEL_SOURCES[suffix])
        index = _motor_names(side).index(motor)
        vector.append(readings[index].value if index < len(readings) else 0.0)
    return vector


def motor_rows(views: Mapping[str, ArmStateView]) -> list[dict[str, Any]]:
    """Per-motor diagnostic rows, for every side whose reader has a thermometer.

    A side whose `temp_mos_c` is None contributes nothing. That is a CAN-free double, which has
    no MOSFET and no rotor — rows of 0 °C would render as a rig of freezing motors.

    Args:
        views: One view per arm side.

    Returns:
        (list[dict]) One row per motor that reported a temperature.
    """
    rows: list[dict[str, Any]] = []
    for side in sorted(views):
        state = views[side].state
        if state is None or state.temp_mos_c is None or state.temp_rotor_c is None:
            continue
        for index, motor in enumerate(_motor_names(side)):
            if index >= len(state.temp_mos_c) or index >= len(state.temp_rotor_c):
                break
            rows.append(
                {
                    MOTOR_ROW_JOINT_NAME: motor,
                    MOTOR_ROW_TEMP_MOS: state.temp_mos_c[index].value,
                    MOTOR_ROW_TEMP_ROTOR: state.temp_rotor_c[index].value,
                }
            )
    return rows


def arm_rows(views: Mapping[str, ArmStateView], stale_after_s: float) -> dict[str, dict[str, Any]]:
    """Per-side liveness: what the guard saw, how old the reading is, and whether that is too old.

    A side that has published nothing is omitted rather than reported with an infinite age. The
    two are different facts — "no reading yet" and "a reading that went stale" — and a client
    that showed them the same way would report a server still starting up as a dead arm.

    `stale` is decided on age alone, which is NOT the rule `ArmStateView.is_driving_blind` uses.
    That one needs a command outliving its reading, because an arm nobody reads and nobody drives
    is idle rather than stale. Here there is no idle case to protect: the board is filled by a
    runner that ticks unconditionally while it lives, so a reading that stopped advancing means
    the runner stopped — and `ArmSessionRunner` keeps that exception to itself until the process
    exits, so this field is the only thing that says so while the server is up.

    Args:
        views: One view per arm side.
        stale_after_s: How old a reading may be before the side is reported stale.

    Returns:
        (dict) Side name to its liveness, for every side that has published.
    """
    rows: dict[str, dict[str, Any]] = {}
    for side in sorted(views):
        view = views[side]
        if view.state is None:
            continue
        rows[side] = {
            ARM_READ_AGE: view.age_s,
            ARM_STALE: view.age_s > stale_after_s,
            ARM_TICK_INDEX: view.state.tick_index,
            ARM_OBSERVATION_PRESENT: view.state.guard.observation_present,
            ARM_BUS_READ_OK: view.state.guard.bus_read_ok,
            ARM_LOCK_ACQUIRED: view.state.guard.lock_acquired,
            ARM_RESIDUAL_EXCEEDED: view.state.guard.residual_exceeded,
        }
    return rows


def joint_rows(views: Mapping[str, ArmStateView]) -> list[dict[str, Any]]:
    """Per-joint readout: the reading, the bounds, and the two verdicts the screen may not make.

    The bounds ride along with the values rather than being fetched once and cached, which for
    numbers that never change looks like waste. It is not: the verdict below is computed FROM
    those bounds, and a client holding a separately fetched copy could render a near-limit
    warning against a bound from a different configuration. One frame, one set of numbers, no
    join across time.

    Radians come from `deg_to_rad`, the single CTR-UNIT crossing, because the browser is
    forbidden from converting — `frontend/src/viewport/state/jointSnapshot.ts` says so, and the
    reason is that a second conversion is a second rounding that disagrees with this one exactly
    where the value sits on a bound.

    A side that has published nothing contributes no rows, on the same rule as everything else
    here: a joint at 0.0° with limits either side of it is indistinguishable from a measurement.

    Args:
        views: One view per arm side, all taken at the same moment.

    Returns:
        (list[dict]) One row per joint of every side that has published, sides in name order and
        joints in the frozen channel declaration's order.
    """
    rows: list[dict[str, Any]] = []
    for side in sorted(views):
        state = views[side].state
        if state is None:
            continue
        limits = soft_limits(side)
        motors = _motor_names(side)
        for index, motor in enumerate(motors):
            if index >= len(limits) or index >= len(state.joint_deg):
                break
            limit = limits[index]
            position = state.joint_deg[index]
            proximity = evaluate_proximity(position, limit, NEAR_LIMIT_MARGIN_DEG)
            rows.append(
                {
                    JOINT_ROW_NAME: limit.mjcf_joint,
                    JOINT_ROW_MOTOR: motor,
                    JOINT_ROW_POSITION_DEG: position.value,
                    JOINT_ROW_POSITION_RAD: deg_to_rad(position).value,
                    JOINT_ROW_VELOCITY_DEG_S: state.velocity_deg_s[index].value,
                    JOINT_ROW_VELOCITY_RAD_S: deg_per_sec_to_rad_per_sec(
                        state.velocity_deg_s[index]
                    ).value,
                    JOINT_ROW_TORQUE_NM: state.torque_nm[index].value,
                    JOINT_ROW_LIMIT_LOWER_DEG: limit.lower_deg.value,
                    JOINT_ROW_LIMIT_UPPER_DEG: limit.upper_deg.value,
                    JOINT_ROW_LIMIT_LOWER_RAD: limit.lower_rad.value,
                    JOINT_ROW_LIMIT_UPPER_RAD: limit.upper_rad.value,
                    JOINT_ROW_NEAR_LIMIT: proximity.near_limit,
                    JOINT_ROW_BLOCKED_DIRECTION: proximity.blocked_direction.value,
                }
            )
    return rows


def telemetry_body(views: Mapping[str, ArmStateView], stale_after_s: float) -> dict[str, Any]:
    """Build the whole `telemetry` body from one read of every board.

    The views are taken by the caller and passed in together, so every part of one frame
    describes the same instant. Reading the boards from inside here, per section, would let the
    observation vector and the arm ages come from different ticks.

    Args:
        views: One view per arm side, all taken at the same moment.
        stale_after_s: How old a reading may be before its side is reported stale.

    Returns:
        (dict) The body, carrying exactly the fields `CTR-WS@v2` declares for this frame.
    """
    return {
        TELEMETRY_SEQUENCE_FIELD: max(
            (view.state.tick_index for view in views.values() if view.state is not None),
            default=0,
        ),
        TELEMETRY_OBSERVATION_FIELD: {OBSERVATION_STATE_KEY: observation_vector(views)},
        TELEMETRY_MOTOR_STATES_FIELD: motor_rows(views),
        TELEMETRY_ARMS_FIELD: arm_rows(views, stale_after_s),
        TELEMETRY_JOINTS_FIELD: joint_rows(views),
    }


__all__ = [
    "ARM_BUS_READ_OK",
    "ARM_LOCK_ACQUIRED",
    "ARM_OBSERVATION_PRESENT",
    "ARM_READ_AGE",
    "ARM_RESIDUAL_EXCEEDED",
    "ARM_STALE",
    "JOINT_ROW_BLOCKED_DIRECTION",
    "JOINT_ROW_LIMIT_LOWER_DEG",
    "JOINT_ROW_LIMIT_LOWER_RAD",
    "JOINT_ROW_LIMIT_UPPER_DEG",
    "JOINT_ROW_LIMIT_UPPER_RAD",
    "JOINT_ROW_MOTOR",
    "JOINT_ROW_NAME",
    "JOINT_ROW_NEAR_LIMIT",
    "JOINT_ROW_POSITION_DEG",
    "JOINT_ROW_POSITION_RAD",
    "JOINT_ROW_TORQUE_NM",
    "JOINT_ROW_VELOCITY_DEG_S",
    "JOINT_ROW_VELOCITY_RAD_S",
    "ARM_TICK_INDEX",
    "MOTOR_ROW_JOINT_NAME",
    "MOTOR_ROW_TEMP_MOS",
    "MOTOR_ROW_TEMP_ROTOR",
    "OBSERVATION_STATE_KEY",
    "arm_rows",
    "joint_rows",
    "motor_rows",
    "observation_vector",
    "telemetry_body",
]
