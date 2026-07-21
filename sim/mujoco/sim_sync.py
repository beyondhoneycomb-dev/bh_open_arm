"""The single LeRobot<->MJCF unit boundary for the MuJoCo backend (WP-0C-01).

`09` §2.10 makes the sim sync a LeRobot `Robot` plugin, and `09` (send_action)
makes the deg->rad conversion the sync's own responsibility: the LeRobot boundary
is degrees, the MJCF boundary is radians (`02a` WP-0C-01 interface contract). The
frozen CTR-UNIT@v1 boundary table (contracts/unit_tags.yaml) names exactly this
module's `lerobot_to_mjcf` as the sole site the deg->rad crossing may occur, so
every degree-to-radian conversion on the action path funnels through this one
function -- a second site is the double-conversion bug FR-SIM-082 exists to forbid.

The observation path crosses the same boundary in reverse (MJCF radians ->
LeRobot degrees). CTR-UNIT@v1 enumerates only the deg->rad crossing for this
boundary, so `mjcf_to_lerobot` performs the reverse crossing through the same
sanctioned CTR-UNIT typed conversions, in this same boundary-owning module. It
never reaches for a raw `math.degrees`: crossing a unit stays a typed, named
operation. The reverse crossing is not yet listed in the frozen table; a
CTR-UNIT@v2 that adds it and its site would close that gap.
"""

from __future__ import annotations

from collections.abc import Mapping

from contracts.action.observation import raw_observation_channels
from contracts.units import (
    Deg,
    Rad,
    RadPerSec,
    deg_to_rad,
    rad_per_sec_to_deg_per_sec,
    rad_to_deg,
)

# The LeRobot channel-name suffixes that split the flattened observation vector
# into its three physical quantities (10 §2.3).
POSITION_SUFFIX = "pos"
VELOCITY_SUFFIX = "vel"
TORQUE_SUFFIX = "torque"

# One motor's radian-space state as MuJoCo reports it: joint position, joint
# velocity, actuator torque. Torque is already Nm at the MJCF boundary and crosses
# no unit boundary, so only position and velocity are converted on the way out.
JointStateRad = tuple[float, float, float]


def action_channel_order(bimanual: bool = True) -> tuple[str, ...]:
    """Return the position action channel names in LeRobot action order.

    These are the `.pos` channels of the frozen observation layout, arm-major
    (`left_*` then `right_*`), motor order joint_1..joint_7 then gripper -- the same
    order the MJCF actuators appear in, so an action index names one joint.

    Args:
        bimanual: Whether to build the 16-channel bimanual order or 8 single arm.

    Returns:
        (tuple[str, ...]) Ordered position action channel names.
    """
    return tuple(
        channel.name
        for channel in raw_observation_channels(bimanual=bimanual)
        if channel.suffix == POSITION_SUFFIX
    )


def lerobot_to_mjcf(action_deg: Mapping[str, float]) -> dict[str, float]:
    """Convert a LeRobot position action (degrees) to MJCF ctrl (radians).

    This is the single sanctioned deg->rad site for the LeRobot<->MJCF boundary
    (CTR-UNIT@v1). Every degree value the backend sends is wrapped as a `Deg`, run
    through the named `deg_to_rad` conversion, and returned as a radian scalar keyed
    by the same channel name, so `MujocoScene.write_ctrl` can address the actuator.

    Args:
        action_deg: Position action channel name to angle in degrees.

    Returns:
        (dict[str, float]) The same channels, values in radians.
    """
    return {name: deg_to_rad(Deg(float(value))).value for name, value in action_deg.items()}


def mjcf_to_lerobot(joint_state: Mapping[str, JointStateRad]) -> dict[str, float]:
    """Convert MJCF radian joint state to the LeRobot degree observation vector.

    Builds the 48 (bimanual) flattened `observation.state` channels: position in
    degrees, velocity in degrees per second, torque in newton-metres. Position and
    velocity cross the LeRobot<->MJCF boundary through the named CTR-UNIT reverse
    conversions; torque is Nm on both sides and crosses no boundary.

    Args:
        joint_state: Motor key (`left_joint_1`, `left_gripper`, ...) to its
            `(position_rad, velocity_rad_s, torque_nm)` triple.

    Returns:
        (dict[str, float]) The 48 named observation channels, in file order,
        each value in the unit its CTR-UNIT tag declares for that index.
    """
    observation: dict[str, float] = {}
    for channel in raw_observation_channels(bimanual=True):
        motor_key = f"{channel.arm}_{channel.motor}" if channel.arm else channel.motor
        position_rad, velocity_rad_s, torque_nm = joint_state[motor_key]
        if channel.suffix == POSITION_SUFFIX:
            observation[channel.name] = rad_to_deg(Rad(position_rad)).value
        elif channel.suffix == VELOCITY_SUFFIX:
            observation[channel.name] = rad_per_sec_to_deg_per_sec(RadPerSec(velocity_rad_s)).value
        else:
            observation[channel.name] = torque_nm
    return observation
