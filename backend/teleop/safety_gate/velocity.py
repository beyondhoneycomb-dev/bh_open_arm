"""The EE cartesian velocity limit (`FR-TEL-037`): clamp the per-tick pose delta.

LeRobot has no velocity limit of any kind. This bounds the end-effector motion
between two consecutive commands so a fast hand or a jump in the pose stream cannot
translate into a fast robot: the linear speed of the translation delta is capped at
`max_linear_vel`, and the angular speed of the rotation delta at `max_angular_vel`,
each measured over the control period `dt`. A delta within both limits passes
unchanged; a delta over a limit is scaled back to exactly the limit along its own
direction, so the command still points where the operator moved, only no faster than
allowed. The ceilings are runtime-tunable (`FR-TEL-037` exposes them in the GUI).
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.teleop.safety_gate.constants import (
    DEFAULT_MAX_ANGULAR_VEL_RAD_S,
    DEFAULT_MAX_LINEAR_VEL_M_S,
)
from backend.teleop.safety_gate.pose import (
    EEPose,
    clamp_rotation_toward,
    geodesic_angle,
    vector_add,
    vector_magnitude,
    vector_scale,
    vector_sub,
)


@dataclass(frozen=True)
class VelocityLimitResult:
    """The outcome of limiting one EE pose step.

    Attributes:
        pose: The admissible pose after linear and angular clamping.
        linear_speed_m_s: The requested linear speed before clamping, m/s.
        angular_speed_rad_s: The requested angular speed before clamping, rad/s.
        linear_limited: Whether the linear delta was scaled down.
        angular_limited: Whether the angular delta was scaled down.
    """

    pose: EEPose
    linear_speed_m_s: float
    angular_speed_rad_s: float
    linear_limited: bool
    angular_limited: bool


class EEVelocityLimiter:
    """Bounds the linear and angular speed of an EE pose step (`FR-TEL-037`).

    Ownership: holds the two ceilings and the control period only; the previous pose
    is supplied per call, so the limiter keeps no trajectory state and one instance
    serves either arm. It never raises on a fast command — limiting, not rejecting,
    is the contract — so the gate always gets an admissible pose back.
    """

    def __init__(
        self,
        dt_sec: float,
        max_linear_vel_m_s: float = DEFAULT_MAX_LINEAR_VEL_M_S,
        max_angular_vel_rad_s: float = DEFAULT_MAX_ANGULAR_VEL_RAD_S,
    ) -> None:
        """Bind the limiter to a control period and the two velocity ceilings.

        Args:
            dt_sec: The control period the speed is measured over; must be positive.
            max_linear_vel_m_s: The EE linear speed ceiling, m/s.
            max_angular_vel_rad_s: The EE angular speed ceiling, rad/s.

        Raises:
            ValueError: If `dt_sec` is not positive or a ceiling is negative.
        """
        if dt_sec <= 0.0:
            raise ValueError(f"control period dt_sec must be positive, got {dt_sec}")
        if max_linear_vel_m_s < 0.0 or max_angular_vel_rad_s < 0.0:
            raise ValueError("velocity ceilings must be non-negative")
        self._dt_sec = dt_sec
        self._max_linear_vel = max_linear_vel_m_s
        self._max_angular_vel = max_angular_vel_rad_s

    def limit(self, previous: EEPose, target: EEPose) -> VelocityLimitResult:
        """Clamp the step from `previous` to `target` to the velocity ceilings.

        Args:
            previous: The pose commanded on the prior tick.
            target: The requested pose this tick.

        Returns:
            (VelocityLimitResult) The admissible pose and the pre-clamp speeds.
        """
        max_linear_step = self._max_linear_vel * self._dt_sec
        max_angular_step = self._max_angular_vel * self._dt_sec

        delta = vector_sub(target.translation, previous.translation)
        distance = vector_magnitude(delta)
        linear_speed = distance / self._dt_sec
        linear_limited = distance > max_linear_step
        if linear_limited:
            scale = max_linear_step / distance
            translation = vector_add(previous.translation, vector_scale(delta, scale))
        else:
            translation = target.translation

        angle = geodesic_angle(previous.rotation, target.rotation)
        angular_speed = angle / self._dt_sec
        angular_limited = angle > max_angular_step
        rotation = clamp_rotation_toward(previous.rotation, target.rotation, max_angular_step)

        return VelocityLimitResult(
            pose=EEPose(rotation=rotation, translation=translation),
            linear_speed_m_s=linear_speed,
            angular_speed_rad_s=angular_speed,
            linear_limited=linear_limited,
            angular_limited=angular_limited,
        )
