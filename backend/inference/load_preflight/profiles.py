"""The two inputs the load preflight compares: a checkpoint and a robot config.

`02c` §2.3 names the inputs `checkpoint` and `robot_config`; this gives them the
concrete shape the gate reads. The robot's observation/action widths are derived
from its two shape-bearing switches — bimanual vs single, and `use_velocity_and_torque`
— which is exactly the FR-INF-070 rule that a config yields one of {8, 16, 24, 48}:
positions are always recorded (8 per arm), and velocity+torque add two more channels
per motor only when the switch is on.

`CheckpointProfile` reduces a checkpoint to the three things the gate needs: its
trained input/output widths and the policy family it was trained as. `from_attachment`
builds one from the committed WP-4B-02 `CheckpointAttachment`, so a real checkpoint's
lineage-recorded shape flows straight in rather than being restated.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from contracts.plugin.config import Side

if TYPE_CHECKING:
    from backend.compat.checkpoint_dataset import CheckpointAttachment

# One follower arm carries eight drivers: seven revolute joints plus the gripper
# (`backend.calibration.schema.MOTOR_ORDER`).
MOTORS_PER_ARM = 8

# Observation channels per motor when velocity and torque are recorded: pos, vel,
# torque. Position-only recording keeps one channel per motor.
FULL_CHANNELS_PER_MOTOR = 3
POSITION_CHANNELS_PER_MOTOR = 1


@dataclass(frozen=True)
class RobotProfile:
    """The robot side of the load check: its shape switches and per-arm limits.

    Attributes:
        bimanual: Whether both arms are present (two-arm widths) or one.
        use_velocity_and_torque: Whether vel/torque channels are recorded, which
            triples the per-motor observation width.
        side: The single-arm side; None means unspecified — which locks the arm to
            +/-5 degrees (FR-INF-037). Ignored when `bimanual` (sides are fixed
            left+right).
        left_joint_limits: The left arm's `motor_key -> (lo, hi)` limits (degrees),
            for the gripper mirror check; None skips the mirror check.
        right_joint_limits: The right arm's limits (degrees).
    """

    bimanual: bool
    use_velocity_and_torque: bool
    side: Side | None
    left_joint_limits: dict[str, tuple[float, float]] | None
    right_joint_limits: dict[str, tuple[float, float]] | None

    def arm_count(self) -> int:
        """Return the number of arms: two when bimanual, one otherwise."""
        return 2 if self.bimanual else 1

    def observation_dim(self) -> int:
        """Return the observation.state width — one of {8, 16, 24, 48} (FR-INF-070)."""
        per_motor = (
            FULL_CHANNELS_PER_MOTOR if self.use_velocity_and_torque else POSITION_CHANNELS_PER_MOTOR
        )
        return MOTORS_PER_ARM * per_motor * self.arm_count()

    def action_dim(self) -> int:
        """Return the action width — position-only, so 8 (single) or 16 (bimanual)."""
        return MOTORS_PER_ARM * POSITION_CHANNELS_PER_MOTOR * self.arm_count()

    @classmethod
    def single(
        cls,
        side: Side | None,
        use_velocity_and_torque: bool,
        joint_limits: dict[str, tuple[float, float]] | None = None,
    ) -> RobotProfile:
        """Build a single-arm profile.

        Args:
            side: The arm side, or None to model the unspecified-side lock.
            use_velocity_and_torque: The observation-width switch.
            joint_limits: The arm's degree limits (no mirror check applies single-arm).

        Returns:
            (RobotProfile) A single-arm profile.
        """
        limits = joint_limits
        return cls(
            bimanual=False,
            use_velocity_and_torque=use_velocity_and_torque,
            side=side,
            left_joint_limits=limits if side is Side.LEFT else None,
            right_joint_limits=limits if side is Side.RIGHT else None,
        )

    @classmethod
    def bimanual_profile(
        cls,
        use_velocity_and_torque: bool,
        left_joint_limits: dict[str, tuple[float, float]] | None = None,
        right_joint_limits: dict[str, tuple[float, float]] | None = None,
    ) -> RobotProfile:
        """Build a bimanual profile carrying both arms' limits for the mirror check.

        Args:
            use_velocity_and_torque: The observation-width switch.
            left_joint_limits: The left arm's degree limits.
            right_joint_limits: The right arm's degree limits.

        Returns:
            (RobotProfile) A bimanual profile.
        """
        return cls(
            bimanual=True,
            use_velocity_and_torque=use_velocity_and_torque,
            side=None,
            left_joint_limits=left_joint_limits,
            right_joint_limits=right_joint_limits,
        )


@dataclass(frozen=True)
class CheckpointProfile:
    """The checkpoint side of the load check: its trained widths and policy family.

    Attributes:
        input_dim: The trained `observation.state` width the checkpoint expects.
        output_dim: The trained `action` width the checkpoint emits.
        policy_id: The policy family the checkpoint was trained as (a WP-4B-01 family
            id), or None to skip the policy-ceiling cross-check.
    """

    input_dim: int
    output_dim: int
    policy_id: str | None

    @classmethod
    def from_attachment(cls, attachment: CheckpointAttachment) -> CheckpointProfile:
        """Build a profile from the committed WP-4B-02 `CheckpointAttachment`.

        The attachment's lineage records the trained `observation.state` names and the
        `action` width, so the checkpoint's real shape flows in rather than being
        restated.

        Args:
            attachment: The WP-4B-02 checkpoint attachment.

        Returns:
            (CheckpointProfile) The reduced checkpoint profile.
        """
        return cls(
            input_dim=len(attachment.state_names()),
            output_dim=attachment.action_dim(),
            policy_id=attachment.policy_id,
        )
