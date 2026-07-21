"""Mode (b) — the read-only digital twin (`09` FR-SIM-099).

The twin mirrors the *real* arm's ``get_observation()`` joint state into the sim
model in real time. It is strictly read-only: it writes joint positions into the
scene for display and residual work, and it **never** commands the robot — there is
no ``send_action`` on this path (acceptance ⑨, enforced statically). CAN is never
opened; the twin only consumes observations another component already read.

Two preconditions gate the twin (acceptance ⑩):

- ``use_velocity_and_torque = true`` (FR-SIM-025b). With it off, ``observation.state``
  collapses to positions only and the velocity/torque residuals silently vanish, so
  the twin refuses to start rather than run a twin whose residuals are quietly gone.
- **Stiff (230-series) gain parity** (FR-SIM-028b). The v2 MJCF position actuators
  are modelled at the stiff gains, so stiff is the only real-arm profile whose
  static/transient response matches the sim; a compliant (70-series) arm poisons the
  residual by the gain gap, so the twin refuses a non-stiff profile.

Mirroring crosses deg→rad through the sanctioned CTR-UNIT conversion (the LeRobot
observation is degrees, the MJCF model is radians).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from contracts.units.conversions import deg_to_rad
from contracts.units.tags import Deg
from sim.mujoco.scene import MujocoScene

# The v2 stiff PD gain profile per arm side: seven joints then the gripper. This is
# `openarm_cell_higher_pd.yaml` (kp[230,230,190,190,30,30,30,10]), the only profile
# whose response matches the MJCF-modelled stiff actuators (`09` FR-SIM-028b).
STIFF_KP = (230.0, 230.0, 190.0, 190.0, 30.0, 30.0, 30.0, 10.0)
STIFF_KD = (2.7, 2.7, 2.2, 2.2, 1.5, 1.5, 1.5, 0.2)

# Gain comparison tolerance; a profile within this of the stiff canon is stiff.
GAIN_TOLERANCE = 1e-6

# The observation channel suffix that carries a joint position (degrees).
_POSITION_SUFFIX = ".pos"


class GainParityError(RuntimeError):
    """Raised when the real arm's PD gains are not the stiff profile (`09` FR-SIM-028b)."""


class VelocityTorqueDisabledError(RuntimeError):
    """Raised when the twin is started with ``use_velocity_and_torque`` off (FR-SIM-025b)."""


def verify_stiff_gain_parity(kp: Sequence[float]) -> None:
    """Refuse a real-arm PD profile that is not the stiff (230-series) canon.

    Args:
        kp: The real arm's per-joint proportional gains (one side, 8 values).

    Raises:
        GainParityError: If the profile differs from the stiff canon, or is the
            wrong length.
    """
    if len(kp) != len(STIFF_KP):
        raise GainParityError(
            f"gain profile has {len(kp)} entries, expected {len(STIFF_KP)} (7 joints + gripper)"
        )
    for index, (actual, expected) in enumerate(zip(kp, STIFF_KP, strict=True)):
        if abs(actual - expected) > GAIN_TOLERANCE:
            raise GainParityError(
                f"gain kp[{index}]={actual} is not the stiff value {expected}; the twin "
                "requires stiff (230-series) parity or the residual is gain-poisoned "
                "(09 FR-SIM-028b)"
            )


def require_velocity_and_torque(enabled: bool) -> None:
    """Refuse to run the twin unless ``use_velocity_and_torque`` is enabled.

    Args:
        enabled: The follower's ``use_velocity_and_torque`` flag.

    Raises:
        VelocityTorqueDisabledError: If disabled (FR-SIM-025b).
    """
    if not enabled:
        raise VelocityTorqueDisabledError(
            "twin requires use_velocity_and_torque=true; with it off the velocity and "
            "torque residuals silently vanish (09 FR-SIM-025b)"
        )


class DigitalTwin:
    """A read-only mirror of the real arm's observation into a MuJoCo scene.

    Ownership/lifecycle: holds one ``MujocoScene`` and one observation source (the
    real follower's ``get_observation`` in production, the WP-0C-05 dummy in tests).
    Read-only by construction — it writes mirrored joint positions into the scene and
    never commands the robot. Not thread-safe; one twin serves one mirror loop.
    """

    def __init__(
        self,
        scene: MujocoScene,
        observation_source: Callable[[], dict[str, float]],
        use_velocity_and_torque: bool,
        real_arm_kp: Sequence[float],
    ) -> None:
        """Bind the scene and source after enforcing the twin's two preconditions.

        Args:
            scene: The MuJoCo scene to mirror into.
            observation_source: Returns the real arm's degree observation dict.
            use_velocity_and_torque: The follower flag; must be True (FR-SIM-025b).
            real_arm_kp: The real arm's per-side PD gains; must be stiff (FR-SIM-028b).

        Raises:
            VelocityTorqueDisabledError: If ``use_velocity_and_torque`` is False.
            GainParityError: If ``real_arm_kp`` is not the stiff profile.
        """
        require_velocity_and_torque(use_velocity_and_torque)
        verify_stiff_gain_parity(real_arm_kp)
        self._scene = scene
        self._observation_source = observation_source

    def mirror(self) -> dict[str, float]:
        """Read the real observation and mirror its joint positions into the scene.

        Reads the source's degree observation, crosses each ``.pos`` channel to
        radians through the sanctioned CTR-UNIT conversion, and writes them as scene
        joint positions. Commands nothing — this is the read-only mirror.

        Returns:
            (dict[str, float]) The mirrored positions in radians, by motor key.
        """
        observation = self._observation_source()
        positions_rad = {
            name[: -len(_POSITION_SUFFIX)]: deg_to_rad(Deg(float(value))).value
            for name, value in observation.items()
            if name.endswith(_POSITION_SUFFIX)
        }
        self._scene.set_joint_positions(positions_rad)
        return positions_rad
