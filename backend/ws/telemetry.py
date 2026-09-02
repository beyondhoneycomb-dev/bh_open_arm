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
from contracts.plugin.robot_abc import raw_observation_channels
from contracts.ws import (
    TELEMETRY_ARMS_FIELD,
    TELEMETRY_MOTOR_STATES_FIELD,
    TELEMETRY_OBSERVATION_FIELD,
    TELEMETRY_SEQUENCE_FIELD,
)

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
    }


__all__ = [
    "ARM_BUS_READ_OK",
    "ARM_LOCK_ACQUIRED",
    "ARM_OBSERVATION_PRESENT",
    "ARM_READ_AGE",
    "ARM_RESIDUAL_EXCEEDED",
    "ARM_STALE",
    "ARM_TICK_INDEX",
    "MOTOR_ROW_JOINT_NAME",
    "MOTOR_ROW_TEMP_MOS",
    "MOTOR_ROW_TEMP_ROTOR",
    "OBSERVATION_STATE_KEY",
    "arm_rows",
    "motor_rows",
    "observation_vector",
    "telemetry_body",
]
