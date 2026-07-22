"""The acceleration-limit precondition on arming residual detection (FR-SAF-014, spec 12 §2.13).

With joint acceleration unbounded, the inertial torque M(q).qddot leaks into the GMO residual and
becomes the dominant false-positive source (spec 12 §2.13). v2.0 `joint_limits.yaml` ships every
joint with `has_acceleration_limits: false` and `max_acceleration: 0.0`, so on stock assets the
limits are off. FR-SAF-014 therefore forbids arming residual detection while they are off: the
system must refuse, or at minimum warn.

This is deliberately a *narrow* gate — only the acceleration-limit precondition. The PG-FRIC-001
model-identification activation gate is WP-2C-02's single owner; this module does not duplicate it.
The default policy is REFUSE, matching the band-wide "default off" stance (plan 02b §3.0) and the
WP-2C-04 negative branch RETRY_WITH_VARIANT — activate the limits, then arm.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from backend.threshold.constants import N_ARM_JOINTS
from backend.threshold.errors import AccelerationLimitError, ThresholdConfigError


class AccelLimitPolicy(Enum):
    """What to do when detection is armed while an enabled joint's accel limit is off.

    REFUSE raises (the default and safest reading of FR-SAF-014); WARN allows arming but returns a
    recorded warning, the "or warn" alternative the requirement permits.
    """

    REFUSE = "REFUSE"
    WARN = "WARN"


@dataclass(frozen=True)
class AccelLimitStatus:
    """The joint acceleration-limit configuration detection is being armed against.

    A joint's limit is active only when it is both declared enabled and given a positive ceiling;
    the v2.0 default of `has_acceleration_limits: false` with `max_acceleration: 0.0` is inactive on
    both counts.

    Attributes:
        has_acceleration_limits: Per-joint `has_acceleration_limits` flag, `N_ARM_JOINTS` wide.
        max_acceleration: Per-joint `max_acceleration` [rad/s^2], `N_ARM_JOINTS` wide.
    """

    has_acceleration_limits: tuple[bool, ...]
    max_acceleration: tuple[float, ...]

    def __post_init__(self) -> None:
        """Refuse a status of the wrong per-joint width.

        Raises:
            ThresholdConfigError: If either array is not `N_ARM_JOINTS` wide.
        """
        if len(self.has_acceleration_limits) != N_ARM_JOINTS:
            raise ThresholdConfigError(
                f"has_acceleration_limits must be {N_ARM_JOINTS} joints wide, "
                f"got {len(self.has_acceleration_limits)}"
            )
        if len(self.max_acceleration) != N_ARM_JOINTS:
            raise ThresholdConfigError(
                f"max_acceleration must be {N_ARM_JOINTS} joints wide, "
                f"got {len(self.max_acceleration)}"
            )

    def active(self) -> tuple[bool, ...]:
        """Per-joint acceleration-limit activity: flag set AND ceiling positive."""
        return tuple(
            self.has_acceleration_limits[joint] and self.max_acceleration[joint] > 0.0
            for joint in range(N_ARM_JOINTS)
        )

    @classmethod
    def v2_default(cls) -> AccelLimitStatus:
        """Return the v2.0 `joint_limits.yaml` reality: limits off, ceilings zero (all inactive)."""
        return cls(
            has_acceleration_limits=(False,) * N_ARM_JOINTS,
            max_acceleration=(0.0,) * N_ARM_JOINTS,
        )

    @classmethod
    def all_active(cls, max_acceleration: float) -> AccelLimitStatus:
        """Return a status with every joint limited to the same positive ceiling.

        Args:
            max_acceleration: The shared per-joint ceiling [rad/s^2]; must be positive.

        Returns:
            (AccelLimitStatus) All joints active at that ceiling.

        Raises:
            ThresholdConfigError: If `max_acceleration` is not positive.
        """
        if max_acceleration <= 0.0:
            raise ThresholdConfigError(
                f"max_acceleration must be positive to be active, got {max_acceleration}"
            )
        return cls(
            has_acceleration_limits=(True,) * N_ARM_JOINTS,
            max_acceleration=(max_acceleration,) * N_ARM_JOINTS,
        )


@dataclass(frozen=True)
class ActivationDecision:
    """The verdict of the acceleration-limit precondition check.

    Attributes:
        allowed: Whether detection may arm.
        disabled_joints: Enabled joints whose acceleration limit is inactive.
        warnings: Human-readable warnings recorded under the WARN policy (empty under REFUSE).
    """

    allowed: bool
    disabled_joints: tuple[int, ...]
    warnings: tuple[str, ...]


def check_acceleration_limit_precondition(
    status: AccelLimitStatus,
    per_joint_enable: tuple[bool, ...],
    policy: AccelLimitPolicy = AccelLimitPolicy.REFUSE,
) -> ActivationDecision:
    """Enforce FR-SAF-014 before residual detection arms.

    A joint blocks arming only when it is both detection-enabled and acceleration-unlimited: a
    disabled joint contributes no residual, so its missing limit is irrelevant.

    Args:
        status: The acceleration-limit configuration.
        per_joint_enable: Per-joint detection enable, `N_ARM_JOINTS` wide.
        policy: REFUSE (default) raises on any offending joint; WARN allows arming with a warning.

    Returns:
        (ActivationDecision) Allowed with no offenders, or allowed-with-warning under WARN.

    Raises:
        ThresholdConfigError: If `per_joint_enable` is the wrong width.
        AccelerationLimitError: Under REFUSE, if any enabled joint's acceleration limit is inactive.
    """
    if len(per_joint_enable) != N_ARM_JOINTS:
        raise ThresholdConfigError(
            f"per_joint_enable must be {N_ARM_JOINTS} joints wide, got {len(per_joint_enable)}"
        )
    active = status.active()
    disabled = tuple(
        joint for joint in range(N_ARM_JOINTS) if per_joint_enable[joint] and not active[joint]
    )

    if not disabled:
        return ActivationDecision(allowed=True, disabled_joints=(), warnings=())

    joint_labels = ", ".join(f"joint{joint + 1}" for joint in disabled)
    message = (
        f"acceleration limits inactive on {joint_labels}: residual detection would be polluted by "
        "inertial torque M(q).qddot (FR-SAF-014). Activate acceleration limits, then arm "
        "(RETRY_WITH_VARIANT)."
    )
    if policy is AccelLimitPolicy.REFUSE:
        raise AccelerationLimitError(message)
    return ActivationDecision(allowed=True, disabled_joints=disabled, warnings=(message,))
