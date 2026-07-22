"""The home-return pre-verify: reuse WP-2D-06's replay pre-verify, one arm at a time.

`02b` WP-2D-07 ② requires a home return to run only after a pre-verify passes and not to
auto-run on failure. The pre-verify is WP-2D-06's — `backend.replay.run_pre_verify`, the
four-check walk (position limit, joint velocity, self-collision, environment-collision) whose
collision half is itself WP-2C-08 (`run_preflight`) — driven over WP-2D-06's
`interpolate_trajectory` with its own velocity and density ceilings. Nothing is
re-implemented here: this module is the home-specific caller of that machinery.

WP-2D-06 is single-arm by design (one side interpolates, the other is held), so a bimanual
home is two legs — each arm to the home posture with the other arm held at home. A home
return is admissible only when both legs pass.
"""

from __future__ import annotations

from collections.abc import Sequence

from backend.home.constants import ARM_JOINT_COUNT
from backend.replay import (
    InterpolatedTrajectory,
    InterpolationMethod,
    PreVerifyResult,
    ReplayWaypoint,
    TrajectorySpec,
    density_step_ceiling_rad,
    interpolate_trajectory,
    run_pre_verify,
    velocity_limits_rad_s,
)


class HomePreflight:
    """The home caller of WP-2D-06's replay interpolator and four-check pre-verify.

    Ownership / threading: stateless apart from the velocity and density ceilings it reads
    once from their single sources at construction; `run_pre_verify` loads its own model per
    call, so one instance is reusable across legs and threads.
    """

    def __init__(
        self,
        requested_margin_m: float | None = None,
        method: InterpolationMethod = InterpolationMethod.LINEAR,
    ) -> None:
        """Read the velocity and density ceilings once from their canonical sources.

        Args:
            requested_margin_m: The collision margin, metres, or None for the `WP-1-06`
                default; passed unchanged to `run_pre_verify`.
            method: The interpolation profile for the home legs; linear by default.
        """
        self._requested_margin_m = requested_margin_m
        self._method = method
        self._velocity_limits = velocity_limits_rad_s()
        self._density_ceiling = density_step_ceiling_rad(requested_margin_m)

    @property
    def method(self) -> InterpolationMethod:
        """The interpolation profile used for the home legs."""
        return self._method

    @property
    def density_step_ceiling_rad(self) -> float:
        """The reused `WP-2C-08` per-step joint displacement ceiling, radians."""
        return self._density_ceiling

    def build_leg(
        self,
        side: str,
        start_arm: Sequence[float],
        waypoints_arm: Sequence[Sequence[float]],
        home_arm: Sequence[float],
        gripper: float,
        other_arm_hold: Sequence[float],
    ) -> InterpolatedTrajectory:
        """Interpolate one arm's path to home through WP-2D-06's interpolator.

        Args:
            side: `"right"` or `"left"` — the arm this leg moves.
            start_arm: The arm's seven start joint angles, radians.
            waypoints_arm: Optional intermediate seven-joint postures the path detours through.
            home_arm: The arm's seven home joint angles, radians.
            gripper: The gripper angle held across the leg, radians.
            other_arm_hold: The stationary arm's seven joint angles, held for the whole leg.

        Returns:
            (InterpolatedTrajectory) The dense, auto-extended single-arm trajectory.
        """
        waypoints = (
            ReplayWaypoint(arm_side=side, q_arm=_arm7(start_arm), gripper=gripper),
            *(
                ReplayWaypoint(arm_side=side, q_arm=_arm7(intermediate), gripper=gripper)
                for intermediate in waypoints_arm
            ),
            ReplayWaypoint(arm_side=side, q_arm=_arm7(home_arm), gripper=gripper),
        )
        spec = TrajectorySpec(
            waypoints=waypoints,
            method=self._method,
            other_arm_hold=_arm7(other_arm_hold),
        )
        return interpolate_trajectory(spec, self._velocity_limits, self._density_ceiling)

    def preverify_leg(
        self,
        side: str,
        start_arm: Sequence[float],
        waypoints_arm: Sequence[Sequence[float]],
        home_arm: Sequence[float],
        gripper: float,
        other_arm_hold: Sequence[float],
    ) -> tuple[InterpolatedTrajectory, PreVerifyResult]:
        """Interpolate one arm's home leg and run WP-2D-06's four-check pre-verify on it.

        Args:
            side: `"right"` or `"left"` — the arm this leg moves.
            start_arm: The arm's seven start joint angles, radians.
            waypoints_arm: Optional intermediate seven-joint postures.
            home_arm: The arm's seven home joint angles, radians.
            gripper: The gripper angle held across the leg, radians.
            other_arm_hold: The stationary arm's seven joint angles.

        Returns:
            (InterpolatedTrajectory) The dense leg trajectory.
            (PreVerifyResult) WP-2D-06's four-check verdict for the leg.
        """
        trajectory = self.build_leg(
            side, start_arm, waypoints_arm, home_arm, gripper, other_arm_hold
        )
        result = run_pre_verify(trajectory, requested_margin_m=self._requested_margin_m)
        return trajectory, result


def _arm7(values: Sequence[float]) -> tuple[float, ...]:
    """Coerce a seven-joint arm vector to a float tuple.

    Args:
        values: Seven joint angles.

    Returns:
        (tuple[float, ...]) The seven angles as floats.

    Raises:
        ValueError: If the sequence is not length `ARM_JOINT_COUNT`.
    """
    coerced = tuple(float(value) for value in values)
    if len(coerced) != ARM_JOINT_COUNT:
        raise ValueError(f"expected {ARM_JOINT_COUNT} arm joints, got {len(coerced)}")
    return coerced
