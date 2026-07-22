"""The home-profile registry and the hardstop-avoidance validation (WP-2D-07).

A home profile is one arm's driver state `q[8]` (seven arm joints then the gripper),
applied identically to both arms. The registry holds named profiles and one active
selection; the default is the FR-MAN-047-adopted `[0, 0, 0, π/2, 0, 0, 0, 0]`.

Validation is where the FR-MAN-047 decision has teeth: every arm joint must sit strictly
inside its soft-limit range, so a profile that places a joint on a mechanical hardstop —
`J4 = 0` above all — is refused rather than stored. The limits are not a second copy: they
are the same LeRobot soft limits the IK override writes into the model (`sim.ik.limits`),
so the home and the jog measure "in range" against one source. The gripper is exempt from
the strict-interior rule because its closed position is its mechanical zero, an intended
boundary, not a hardstop to avoid.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.home.constants import (
    ARM_JOINT_COUNT,
    DEFAULT_HOME_PROFILE_NAME,
    DEFAULT_HOME_Q_URDF,
    GRIPPER_INDEX,
    J4_INDEX,
    LIMIT_INTERIOR_EPS_RAD,
    PROFILE_WIDTH,
    SESSION_STOP_PROFILE_NAME,
)
from sim.ik.limits import SIDES, soft_limits


class HomeProfileError(Exception):
    """Raised when a home profile is malformed or sits on a mechanical hardstop.

    A home must be a valid rest pose. A wrong width, or an arm joint on a hardstop (the
    FR-MAN-047 failure the `J4 = 0` MoveIt state would be), is refused here rather than
    handed to a home return that would drive the arm onto the stop.
    """


@dataclass(frozen=True)
class JointLimitMargin:
    """How far one joint of a home profile sits from its soft-limit bounds.

    Attributes:
        joint: The fully-qualified MJCF joint name.
        value_rad: The profile's angle for this joint, radians.
        lower_rad: Soft-limit lower bound, radians.
        upper_rad: Soft-limit upper bound, radians.
        margin_rad: Distance to the nearer bound; negative means outside the range.
        at_hardstop: True when an arm joint is within tolerance of a bound (a hardstop).
            Always False for the gripper, whose closed position is a legitimate bound.
    """

    joint: str
    value_rad: float
    lower_rad: float
    upper_rad: float
    margin_rad: float
    at_hardstop: bool

    def as_record(self) -> dict[str, Any]:
        """Render the margin for an artifact.

        Returns:
            (dict[str, Any]) Every field of the margin.
        """
        return {
            "joint": self.joint,
            "value_rad": self.value_rad,
            "lower_rad": self.lower_rad,
            "upper_rad": self.upper_rad,
            "margin_rad": self.margin_rad,
            "at_hardstop": self.at_hardstop,
        }


@dataclass(frozen=True)
class HomeProfile:
    """One home pose: a per-arm driver state applied identically to both arms.

    Attributes:
        name: The profile name shown before a home return runs.
        q_urdf: The arm's driver state `q[8]` — joint1..joint7 then the gripper, radians.
    """

    name: str
    q_urdf: tuple[float, ...]

    def right_arm(self) -> tuple[float, ...]:
        """Return the seven right-arm joint angles (radians)."""
        return tuple(self.q_urdf[:ARM_JOINT_COUNT])

    def left_arm(self) -> tuple[float, ...]:
        """Return the seven left-arm joint angles (radians); identical to the right arm."""
        return tuple(self.q_urdf[:ARM_JOINT_COUNT])

    def gripper(self) -> float:
        """Return the gripper angle (radians)."""
        return float(self.q_urdf[GRIPPER_INDEX])

    def j4_angle_rad(self) -> float:
        """Return the joint4 (elbow) angle — the FR-MAN-047 quantity, radians."""
        return float(self.q_urdf[J4_INDEX])

    def posture14(self) -> tuple[float, ...]:
        """Return the collision-relevant DOF as right seven then left seven arm joints."""
        return (*self.right_arm(), *self.left_arm())

    def as_record(self) -> dict[str, Any]:
        """Render the profile for an artifact.

        Returns:
            (dict[str, Any]) The name, the driver state, and the joint4 angle.
        """
        return {
            "name": self.name,
            "q_urdf": list(self.q_urdf),
            "j4_angle_rad": self.j4_angle_rad(),
        }


def limit_margins(profile: HomeProfile) -> tuple[JointLimitMargin, ...]:
    """Compute each joint's distance to its soft-limit bounds, for both arms.

    The profile is applied to both arms, and the two arms carry different (mirrored)
    limits, so each side is evaluated against its own limit set.

    Args:
        profile: The home profile.

    Returns:
        (tuple[JointLimitMargin, ...]) One margin per arm joint and gripper, right arm
        first then left, in joint1..joint7 then gripper order.

    Raises:
        HomeProfileError: If the profile width is not `PROFILE_WIDTH`.
    """
    if len(profile.q_urdf) != PROFILE_WIDTH:
        raise HomeProfileError(
            f"home profile {profile.name!r} must hold {PROFILE_WIDTH} values "
            f"(seven arm joints then the gripper), got {len(profile.q_urdf)}"
        )
    margins: list[JointLimitMargin] = []
    for side in SIDES:
        limits = soft_limits(side)
        for index, limit in enumerate(limits):
            lower = limit.lower_rad.value
            upper = limit.upper_rad.value
            value = float(profile.q_urdf[index])
            is_arm_joint = index < ARM_JOINT_COUNT
            at_hardstop = is_arm_joint and (
                value <= lower + LIMIT_INTERIOR_EPS_RAD or value >= upper - LIMIT_INTERIOR_EPS_RAD
            )
            margins.append(
                JointLimitMargin(
                    joint=limit.mjcf_joint,
                    value_rad=value,
                    lower_rad=lower,
                    upper_rad=upper,
                    margin_rad=min(value - lower, upper - value),
                    at_hardstop=at_hardstop,
                )
            )
    return tuple(margins)


def validate_home_profile(profile: HomeProfile) -> tuple[JointLimitMargin, ...]:
    """Validate a home profile, refusing a hardstop or an out-of-range joint.

    Args:
        profile: The home profile.

    Returns:
        (tuple[JointLimitMargin, ...]) The per-joint margins, all admissible on return.

    Raises:
        HomeProfileError: If the width is wrong (③ hardstop), an arm joint sits on a
            mechanical hardstop, or a joint lies outside its soft-limit range.
    """
    margins = limit_margins(profile)
    hardstops = [margin for margin in margins if margin.at_hardstop]
    if hardstops:
        joints = ", ".join(f"{margin.joint}={margin.value_rad:.4f}" for margin in hardstops)
        raise HomeProfileError(
            f"home profile {profile.name!r} places arm joint(s) on a mechanical hardstop: "
            f"{joints}; a home must sit strictly inside the range (FR-MAN-047 — J4=0 is the "
            "lower hardstop, not a home)"
        )
    out_of_range = [margin for margin in margins if margin.margin_rad < -LIMIT_INTERIOR_EPS_RAD]
    if out_of_range:
        joints = ", ".join(
            f"{margin.joint}={margin.value_rad:.4f} outside "
            f"[{margin.lower_rad:.4f}, {margin.upper_rad:.4f}]"
            for margin in out_of_range
        )
        raise HomeProfileError(
            f"home profile {profile.name!r} lies outside the soft-limit range: {joints}"
        )
    return margins


def default_home_profile() -> HomeProfile:
    """Return the FR-MAN-047-adopted default home `[0, 0, 0, π/2, 0, 0, 0, 0]`, validated.

    Returns:
        (HomeProfile) The default home; its joint4 is π/2, never the J4=0 hardstop.
    """
    profile = HomeProfile(name=DEFAULT_HOME_PROFILE_NAME, q_urdf=DEFAULT_HOME_Q_URDF)
    validate_home_profile(profile)
    return profile


def session_stop_profile() -> HomeProfile:
    """Return the session-end stop posture, validated.

    The `openarm_driver` `stop` posture is identical to its `initial`/home pose
    (`04` §3.5 records the stop posture as the same pose), so the session-end stop is the
    home posture under its own name; commanding it goes through the same pre-verified
    home-return machinery.

    Returns:
        (HomeProfile) The stop posture, equal to the default home.
    """
    profile = HomeProfile(name=SESSION_STOP_PROFILE_NAME, q_urdf=DEFAULT_HOME_Q_URDF)
    validate_home_profile(profile)
    return profile


class HomeProfileRegistry:
    """A named registry of home profiles with one active selection.

    Every registered profile is validated on entry, so an invalid home cannot enter the
    registry and later become the active target of a home return. The active profile is
    the one whose name and target posture are shown before a home return runs (①).
    """

    def __init__(self) -> None:
        """Create an empty registry with no active profile."""
        self._profiles: dict[str, HomeProfile] = {}
        self._active: str | None = None

    def register(self, profile: HomeProfile, activate: bool = False) -> None:
        """Validate and store a profile, optionally making it the active one.

        Args:
            profile: The profile to register.
            activate: Whether to make it active. The first profile registered becomes
                active regardless, so the registry is never left without an active home.

        Raises:
            HomeProfileError: If the profile fails validation.
        """
        validate_home_profile(profile)
        self._profiles[profile.name] = profile
        if activate or self._active is None:
            self._active = profile.name

    def get(self, name: str) -> HomeProfile:
        """Return a registered profile by name.

        Args:
            name: The profile name.

        Returns:
            (HomeProfile) The named profile.

        Raises:
            HomeProfileError: If no profile is registered under that name.
        """
        if name not in self._profiles:
            raise HomeProfileError(f"no home profile named {name!r}; have {self.names()}")
        return self._profiles[name]

    def names(self) -> tuple[str, ...]:
        """Return the registered profile names in registration order."""
        return tuple(self._profiles)

    @property
    def active(self) -> HomeProfile:
        """Return the active home profile.

        Raises:
            HomeProfileError: If the registry holds no profile.
        """
        if self._active is None:
            raise HomeProfileError("registry holds no home profile; register one first")
        return self._profiles[self._active]

    def set_active(self, name: str) -> None:
        """Make a registered profile the active one.

        Args:
            name: The profile name.

        Raises:
            HomeProfileError: If no profile is registered under that name.
        """
        if name not in self._profiles:
            raise HomeProfileError(f"no home profile named {name!r}; have {self.names()}")
        self._active = name

    def as_record(self) -> dict[str, Any]:
        """Render the registry for an artifact.

        Returns:
            (dict[str, Any]) The active name and every registered profile.
        """
        return {
            "active": self._active,
            "profiles": [profile.as_record() for profile in self._profiles.values()],
        }


def default_registry() -> HomeProfileRegistry:
    """Return a registry seeded with the default home as the active profile.

    Returns:
        (HomeProfileRegistry) A registry whose active profile is the FR-MAN-047 default.
    """
    registry = HomeProfileRegistry()
    registry.register(default_home_profile(), activate=True)
    return registry
