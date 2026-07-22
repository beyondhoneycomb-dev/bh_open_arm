"""The home-return button and its no-auto-run guard (WP-2D-07).

Three acceptance rules shape this module (`02b` WP-2D-07):

- ① the active home-profile name and its target posture are shown *before* execution, so
  every plan carries a `HomePreview` (name, joint target, resulting EE pose, limit margins)
  whether or not the pre-verify passes;
- ② a failed pre-verify does not auto-run — the plan is non-executable and demands an
  intermediate waypoint, and asking a blocked plan for its trajectory raises;
- the session-end stop posture rides the same path (its target is the stop profile, equal to
  the home).

A bimanual home is two legs — each arm to home with the other held at home — through the
reused WP-2D-06 pre-verify (`HomePreflight`, which wraps `backend.replay.run_pre_verify`).
The EE pose in the preview is FK over the reused WP-2D-01 `KinematicFrames`. Both reuses keep
one source of truth for interpolation, collision, and kinematics.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from backend.cartesian_jog.frames import KinematicFrames
from backend.home.constants import ARM_JOINT_COUNT
from backend.home.preverify import HomePreflight
from backend.home.profile import (
    HomeProfile,
    HomeProfileRegistry,
    JointLimitMargin,
    session_stop_profile,
    validate_home_profile,
)
from backend.replay import InterpolatedTrajectory, PreVerifyResult

SIDE_RIGHT = "right"
SIDE_LEFT = "left"


class HomeReturnBlockedError(Exception):
    """Raised when an executable trajectory is requested from a blocked home-return plan.

    A plan whose pre-verify failed must not auto-run (`02b` WP-2D-07 ②), so the trajectory it
    would have executed is withheld: asking for it is the caller trying to run a home return
    the pre-verify refused, and that must fail loudly, not hand back a path.
    """


@dataclass(frozen=True)
class HomePreview:
    """What is shown before a home return runs: the active home and its target (①).

    Attributes:
        profile_name: The active home-profile name.
        q_urdf: The target driver state `q[8]` for one arm (applied to both).
        j4_angle_rad: The joint4 (elbow) target — π/2 for the default, never the hardstop.
        ee_pose_right: The right EE world pose at the target, `[px, py, pz, qw, qx, qy, qz]`.
        ee_pose_left: The left EE world pose at the target.
        limit_margins: Each target joint's distance to its soft-limit bounds.
    """

    profile_name: str
    q_urdf: tuple[float, ...]
    j4_angle_rad: float
    ee_pose_right: tuple[float, ...]
    ee_pose_left: tuple[float, ...]
    limit_margins: tuple[JointLimitMargin, ...]

    def as_record(self) -> dict[str, Any]:
        """Render the preview for an artifact.

        Returns:
            (dict[str, Any]) The name, target posture, EE poses, and limit margins.
        """
        return {
            "profile_name": self.profile_name,
            "q_urdf": list(self.q_urdf),
            "j4_angle_rad": self.j4_angle_rad,
            "ee_pose_right": list(self.ee_pose_right),
            "ee_pose_left": list(self.ee_pose_left),
            "limit_margins": [margin.as_record() for margin in self.limit_margins],
        }


def build_home_preview(profile: HomeProfile, frames: KinematicFrames) -> HomePreview:
    """Build the pre-execution preview for a home profile (①).

    Validates the profile (so an invalid home never reaches a preview), then reads the EE
    pose the target produces through the reused FK context.

    Args:
        profile: The home profile whose target is previewed.
        frames: The reused WP-2D-01 FK context.

    Returns:
        (HomePreview) The name, target posture, EE poses, and limit margins.

    Raises:
        HomeProfileError: If the profile is invalid (wrong width or a hardstop joint).
    """
    margins = validate_home_profile(profile)
    solution16 = np.array([*profile.q_urdf, *profile.q_urdf], dtype=float)
    ee_right = tuple(float(value) for value in frames.control_point_pose("right", solution16, 0.0))
    ee_left = tuple(float(value) for value in frames.control_point_pose("left", solution16, 0.0))
    return HomePreview(
        profile_name=profile.name,
        q_urdf=tuple(profile.q_urdf),
        j4_angle_rad=profile.j4_angle_rad(),
        ee_pose_right=ee_right,
        ee_pose_left=ee_left,
        limit_margins=margins,
    )


@dataclass(frozen=True)
class HomeLeg:
    """One arm's home leg: its trajectory and the reused WP-2D-06 pre-verify verdict.

    Attributes:
        side: `"right"` or `"left"`.
        verdict: WP-2D-06's four-check verdict for this leg.
        trajectory: The dense single-arm trajectory the leg would execute.
    """

    side: str
    verdict: PreVerifyResult
    trajectory: InterpolatedTrajectory

    @property
    def ok(self) -> bool:
        """Whether this leg's pre-verify passed."""
        return self.verdict.ok

    def as_record(self) -> dict[str, Any]:
        """Render the leg for an evidence artifact.

        Returns:
            (dict[str, Any]) The side, verdict summary, and sample count.
        """
        return {
            "side": self.side,
            "ok": self.verdict.ok,
            "category": None if self.verdict.category is None else self.verdict.category.value,
            "first_violation_index": self.verdict.first_violation_index,
            "detail": self.verdict.detail,
            "residual_note": self.verdict.residual_note,
            "sample_count": len(self.trajectory),
        }


@dataclass(frozen=True)
class HomeReturnPlan:
    """One home-return plan: what would run, whether it may, and why (`02b` WP-2D-07).

    Attributes:
        preview: The active home and its target, shown before execution (①).
        legs: The right and left home legs, each with its pre-verify verdict.
        executable: True only when both legs' pre-verify passed.
        requires_waypoint: True when a failed pre-verify demands an intermediate waypoint.
        reason: The plan's disposition in words.
    """

    preview: HomePreview
    legs: tuple[HomeLeg, HomeLeg]
    executable: bool
    requires_waypoint: bool
    reason: str

    def executable_trajectory(self) -> tuple[InterpolatedTrajectory, InterpolatedTrajectory]:
        """Return the per-arm trajectories to execute, refusing when blocked (②).

        Returns:
            (tuple[InterpolatedTrajectory, InterpolatedTrajectory]) The right then left leg
            trajectories, executed one arm at a time.

        Raises:
            HomeReturnBlockedError: If either leg's pre-verify failed — the home return must
                not auto-run, so the withheld trajectory cannot be obtained.
        """
        if not self.executable:
            raise HomeReturnBlockedError(self.reason)
        return (self.legs[0].trajectory, self.legs[1].trajectory)

    def as_record(self) -> dict[str, Any]:
        """Render the plan for an evidence artifact.

        Returns:
            (dict[str, Any]) The preview, both legs, and the disposition.
        """
        return {
            "preview": self.preview.as_record(),
            "legs": [leg.as_record() for leg in self.legs],
            "executable": self.executable,
            "requires_waypoint": self.requires_waypoint,
            "reason": self.reason,
        }


class HomeReturn:
    """The home-return button: preview, pre-verify, and the no-auto-run guard (WP-2D-07).

    Ownership: holds the profile registry, one `HomePreflight` (the reused WP-2D-06 walk),
    and one `KinematicFrames` (the reused WP-2D-01 FK). All three are single-thread; one
    `HomeReturn` serves one operator session.
    """

    def __init__(
        self, registry: HomeProfileRegistry, preflight: HomePreflight, frames: KinematicFrames
    ) -> None:
        """Bind the registry, the reused pre-verify walk, and the reused FK context."""
        self._registry = registry
        self._preflight = preflight
        self._frames = frames

    def preview(self, target: HomeProfile | None = None) -> HomePreview:
        """Return the pre-execution preview for the active (or a given) home profile (①).

        Args:
            target: The profile to preview, or None for the active one.

        Returns:
            (HomePreview) The name, target posture, EE poses, and limit margins.
        """
        return build_home_preview(target or self._registry.active, self._frames)

    def plan_return(
        self,
        start_posture14: Sequence[float],
        waypoints: Sequence[Sequence[float]] = (),
        target: HomeProfile | None = None,
    ) -> HomeReturnPlan:
        """Plan a home return, gating execution on the reused pre-verify (`02b` WP-2D-07).

        The preview is built first and always, so the active home and its target posture are
        shown before anything runs (①). Each arm is pre-verified to home with the other held
        at home; on any failure the plan is non-executable and asks for a waypoint (②).

        Args:
            start_posture14: The current arm state, right seven then left seven joints.
            waypoints: Optional intermediate postures (each a 14-vector, right seven then
                left seven) the path detours through, re-verified as part of each leg.
            target: The home profile to return to, or None for the active one.

        Returns:
            (HomeReturnPlan) The preview, both legs' verdicts, and whether it may run.
        """
        target_profile = target or self._registry.active
        home_arm = target_profile.right_arm()
        gripper = target_profile.gripper()
        preview = build_home_preview(target_profile, self._frames)

        start_right, start_left = _split(start_posture14)
        waypoints_right = [_split(waypoint)[0] for waypoint in waypoints]
        waypoints_left = [_split(waypoint)[1] for waypoint in waypoints]

        right_traj, right_verdict = self._preflight.preverify_leg(
            SIDE_RIGHT, start_right, waypoints_right, home_arm, gripper, other_arm_hold=home_arm
        )
        left_traj, left_verdict = self._preflight.preverify_leg(
            SIDE_LEFT, start_left, waypoints_left, home_arm, gripper, other_arm_hold=home_arm
        )
        legs = (
            HomeLeg(side=SIDE_RIGHT, verdict=right_verdict, trajectory=right_traj),
            HomeLeg(side=SIDE_LEFT, verdict=left_verdict, trajectory=left_traj),
        )

        executable = right_verdict.ok and left_verdict.ok
        if executable:
            reason = "pre-verify passed on both arms; home return admissible"
        else:
            failed = [leg for leg in legs if not leg.ok]
            reason = (
                "pre-verify failed ("
                + "; ".join(f"{leg.side}: {leg.verdict.detail}" for leg in failed)
                + "); home return will not auto-run — specify an intermediate waypoint and re-plan"
            )
        return HomeReturnPlan(
            preview=preview,
            legs=legs,
            executable=executable,
            requires_waypoint=not executable,
            reason=reason,
        )

    def plan_session_stop(
        self, start_posture14: Sequence[float], waypoints: Sequence[Sequence[float]] = ()
    ) -> HomeReturnPlan:
        """Plan the session-end stop, to the stop posture, through the same guard.

        The stop posture equals the home (`04` §3.5), so this is a home return whose target is
        the stop profile; it is pre-verified and non-auto-running exactly as a home return is.

        Args:
            start_posture14: The current arm state, right seven then left seven joints.
            waypoints: Optional intermediate postures.

        Returns:
            (HomeReturnPlan) The stop-posture plan.
        """
        return self.plan_return(start_posture14, waypoints, target=session_stop_profile())


def _split(posture14: Sequence[float]) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Split a 14-vector into right then left seven-joint arm vectors.

    Args:
        posture14: Right-arm joint1..joint7 followed by left-arm joint1..joint7.

    Returns:
        (tuple[float, ...]) The right seven joints.
        (tuple[float, ...]) The left seven joints.

    Raises:
        ValueError: If the vector is not fourteen values wide.
    """
    values = tuple(float(value) for value in posture14)
    if len(values) != ARM_JOINT_COUNT * 2:
        raise ValueError(f"posture must hold {ARM_JOINT_COUNT * 2} joints, got {len(values)}")
    return values[:ARM_JOINT_COUNT], values[ARM_JOINT_COUNT:]
