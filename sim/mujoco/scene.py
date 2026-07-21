"""The MuJoCo scene for the OpenArm bimanual backend (WP-0C-01).

The only module that touches the `mujoco` package. It loads the WP-0C-03-corrected
v2 asset (sim/mjcf/v2/openarm_bimanual.xml -- the single asset SoT, J7 = DM4310),
and exposes the two operations the LeRobot backend needs: write position-actuator
ctrl, and read joint state. Both speak radians; the deg<->rad crossing lives in
`sim.mujoco.sim_sync`, so this module stays in the MJCF's own unit throughout.

The channel<->actuator and channel<->joint maps are built once at load by walking
the model's actuators, and are checked against the frozen CTR-ACT channel set: if
the asset ever stops matching the contract (a renamed joint, a dropped actuator),
load fails loudly here rather than silently observing the wrong joint.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from pathlib import Path

import mujoco
import sim.mjcf
from contracts.action.observation import raw_observation_channels
from sim.mujoco.sim_sync import POSITION_SUFFIX, JointStateRad, action_channel_order

# The single asset SoT is WP-0C-03's package (sim/mjcf/**); this backend consumes
# its J7-corrected v2 bimanual model. Resolving the path through the `sim.mjcf`
# package -- rather than a hand-built relative path -- keeps the asset dependency a
# real, visible import: if WP-0C-03 relocates the asset, this follows it.
_MJCF_PATH = Path(sim.mjcf.__file__).resolve().parent / "v2" / "openarm_bimanual.xml"

# MJCF joint names map to CTR-ACT motor keys: joint1..joint7 become joint_1..joint_7,
# and the actuated first finger joint is the gripper motor. The second finger joint
# is an unactuated coupled joint with no actuator, so it never reaches these maps.
_ARM_JOINT = re.compile(r"^openarm_(left|right)_joint([1-7])$")
_ARM_GRIPPER = re.compile(r"^openarm_(left|right)_finger_joint1$")
_GRIPPER_MOTOR = "gripper"

# The CTR-ACT motor keys and position action channels the asset must cover exactly.
_EXPECTED_MOTOR_KEYS = frozenset(
    f"{channel.arm}_{channel.motor}" for channel in raw_observation_channels(bimanual=True)
)
_EXPECTED_ACTION_CHANNELS = frozenset(action_channel_order(bimanual=True))


def default_mjcf_path() -> Path:
    """Return the path to the WP-0C-03-corrected v2 bimanual MJCF asset."""
    return _MJCF_PATH


def _motor_key(joint_name: str) -> str | None:
    """Map an MJCF joint name to its CTR-ACT motor key, or None if unactuated.

    Args:
        joint_name: MJCF joint name, e.g. `openarm_left_joint1`.

    Returns:
        (str | None) The motor key (`left_joint_1`, `left_gripper`), or None for a
        joint that carries no motor in the contract (the coupled second finger).
    """
    joint_match = _ARM_JOINT.match(joint_name)
    if joint_match:
        arm, number = joint_match.groups()
        return f"{arm}_joint_{number}"
    gripper_match = _ARM_GRIPPER.match(joint_name)
    if gripper_match:
        return f"{gripper_match.group(1)}_{_GRIPPER_MOTOR}"
    return None


class MujocoScene:
    """A loaded OpenArm bimanual MuJoCo model and its channel maps (WP-0C-01).

    Ownership: the scene owns its `MjModel`/`MjData`; the backend holds one scene
    while connected and drops it on disconnect. Not thread-safe -- one control loop
    steps it. All quantities crossing this class are radians and newton-metres (the
    MJCF boundary); unit crossing to LeRobot degrees is the caller's, via
    `sim.mujoco.sim_sync`.
    """

    def __init__(
        self,
        model: mujoco.MjModel,
        data: mujoco.MjData,
        ctrl_index: Mapping[str, int],
        motor_index: Mapping[str, tuple[int, int, int]],
    ) -> None:
        """Bind a compiled model, its data, and the pre-built channel maps.

        Args:
            model: The compiled MJCF model.
            data: The model's mutable state.
            ctrl_index: Position action channel name to actuator index.
            motor_index: Motor key to `(qpos_address, dof_address, actuator_index)`.
        """
        self._model = model
        self._data = data
        self._ctrl_index = dict(ctrl_index)
        self._motor_index = dict(motor_index)

    @classmethod
    def load(cls, mjcf_path: Path | None = None) -> MujocoScene:
        """Compile the asset and build the channel maps, checked against CTR-ACT.

        Args:
            mjcf_path: Asset override; defaults to the WP-0C-03 v2 bimanual model.

        Returns:
            (MujocoScene) A loaded scene reset to its home configuration.

        Raises:
            ValueError: If the asset's actuated joints do not match the frozen
                CTR-ACT channel set exactly.
        """
        path = mjcf_path or _MJCF_PATH
        model = mujoco.MjModel.from_xml_path(str(path))
        data = mujoco.MjData(model)

        ctrl_index: dict[str, int] = {}
        motor_index: dict[str, tuple[int, int, int]] = {}
        for actuator in range(model.nu):
            joint_id = int(model.actuator_trnid[actuator, 0])
            joint_name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, joint_id)
            motor_key = _motor_key(joint_name) if joint_name else None
            if motor_key is None:
                raise ValueError(
                    f"actuator {actuator} drives joint '{joint_name}', which is not a "
                    "CTR-ACT motor; the asset no longer matches the action contract"
                )
            ctrl_index[f"{motor_key}.{POSITION_SUFFIX}"] = actuator
            motor_index[motor_key] = (
                int(model.jnt_qposadr[joint_id]),
                int(model.jnt_dofadr[joint_id]),
                actuator,
            )

        _verify_channel_coverage(ctrl_index.keys(), motor_index.keys())

        scene = cls(model, data, ctrl_index, motor_index)
        scene.reset()
        return scene

    def reset(self) -> None:
        """Reset to the model's home configuration and refresh derived quantities."""
        mujoco.mj_resetData(self._model, self._data)
        mujoco.mj_forward(self._model, self._data)

    def write_ctrl(self, ctrl_rad: Mapping[str, float]) -> dict[str, float]:
        """Write position-actuator ctrl in radians, clamped to each actuator range.

        Args:
            ctrl_rad: Position action channel name to target angle in radians.

        Returns:
            (dict[str, float]) The clamped radian target actually written per channel.
        """
        accepted: dict[str, float] = {}
        for name, value in ctrl_rad.items():
            actuator = self._ctrl_index[name]
            low, high = self._model.actuator_ctrlrange[actuator]
            clamped = min(max(value, float(low)), float(high))
            self._data.ctrl[actuator] = clamped
            accepted[name] = clamped
        mujoco.mj_forward(self._model, self._data)
        return accepted

    def read_joint_state(self) -> dict[str, JointStateRad]:
        """Read every motor's radian-space state: position, velocity, torque.

        Returns:
            (dict[str, JointStateRad]) Motor key to `(position_rad, velocity_rad_s,
            torque_nm)`. Torque is the actuator generalised force on the joint's dof.
        """
        state: dict[str, JointStateRad] = {}
        for motor_key, (qpos_address, dof_address, _) in self._motor_index.items():
            state[motor_key] = (
                float(self._data.qpos[qpos_address]),
                float(self._data.qvel[dof_address]),
                float(self._data.qfrc_actuator[dof_address]),
            )
        return state

    def set_joint_positions(self, positions_rad: Mapping[str, float]) -> None:
        """Set joint positions directly, in radians, and refresh derived quantities.

        A test seam for driving the scene to a known configuration without stepping
        dynamics, so an observation round-trip can assert against an exact input.

        Args:
            positions_rad: Motor key to joint position in radians.
        """
        for motor_key, value in positions_rad.items():
            qpos_address, _, _ = self._motor_index[motor_key]
            self._data.qpos[qpos_address] = value
        mujoco.mj_forward(self._model, self._data)


def _verify_channel_coverage(action_channels: Iterable[str], motor_keys: Iterable[str]) -> None:
    """Fail unless the built maps cover exactly the frozen CTR-ACT channel set.

    Args:
        action_channels: The position action channel names the asset produced.
        motor_keys: The motor keys the asset produced.

    Raises:
        ValueError: If either set differs from the contract's.
    """
    built_actions = frozenset(action_channels)
    built_motors = frozenset(motor_keys)
    if built_actions != _EXPECTED_ACTION_CHANNELS:
        raise ValueError(
            "MJCF actuators do not match CTR-ACT action channels: "
            f"missing={_EXPECTED_ACTION_CHANNELS - built_actions}, "
            f"extra={built_actions - _EXPECTED_ACTION_CHANNELS}"
        )
    if built_motors != _EXPECTED_MOTOR_KEYS:
        raise ValueError(
            "MJCF actuated joints do not match CTR-ACT motors: "
            f"missing={_EXPECTED_MOTOR_KEYS - built_motors}, "
            f"extra={built_motors - _EXPECTED_MOTOR_KEYS}"
        )
