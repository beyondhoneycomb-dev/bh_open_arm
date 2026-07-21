"""OpenArm plugin config and its assembly-time validation (CTR-PLUG@v1).

Two config mistakes fail LeRobot only at runtime, deep in a record loop, and the
plugin contract moves both to config-assembly time where the message is clear
(01 §4.2 T1, OA-SYS-005/006):

- `side` unset. Without `--robot.side=left|right` the follower's `joint_limits`
  default to +/-5 degrees and the arm effectively does not move (01 FR-SYS-013).
  So `side` is required, no default; an unset side is refused at construction.
- `use_velocity_and_torque` mismatched between follower and leader. LeRobot then
  dies with a `KeyError` on `joint_1.torque` inside `build_dataset_frame`
  (01 FR-SYS-012). So the two must agree, and the bimanual follower must apply the
  flag to BOTH arms; a mismatch is refused before any session starts.

This module imports no robot stack: config validation is pure and stays in the
light lane, so the acceptance fixtures run without LeRobot present.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Side(Enum):
    """Which arm a single-arm follower drives (01 FR-SYS-013)."""

    LEFT = "left"
    RIGHT = "right"


class ConfigError(ValueError):
    """Raised when a plugin config is rejected at assembly time."""


@dataclass(frozen=True)
class FollowerConfig:
    """One OpenArm follower arm's config.

    `side` has no default on purpose: the LeRobot default (+/-5 degree limits) is
    unusable, so the value must be stated (01 FR-SYS-013).

    Attributes:
        side: Which arm this follower drives.
        use_velocity_and_torque: Whether velocity and torque channels are recorded
            (01 FR-SYS-012). Must match the leader.
    """

    side: Side
    use_velocity_and_torque: bool

    def __post_init__(self) -> None:
        """Reject a follower whose side was left unset (passed as None)."""
        if self.side is None:
            raise ConfigError(
                "follower config requires `side` (left|right); the +/-5 degree default is unusable "
                "(01 FR-SYS-013)"
            )


@dataclass(frozen=True)
class LeaderConfig:
    """A teleoperator (leader) config.

    Attributes:
        use_velocity_and_torque: Whether velocity and torque channels are recorded.
            Must match every follower (01 FR-SYS-012).
    """

    use_velocity_and_torque: bool


def validate_teleop_pairing(follower: FollowerConfig, leader: LeaderConfig) -> None:
    """Reject a follower/leader pair whose velocity-torque switch disagrees.

    Args:
        follower: The follower arm config.
        leader: The teleoperator config.

    Raises:
        ConfigError: If the two do not share one `use_velocity_and_torque` value.
    """
    if follower.use_velocity_and_torque != leader.use_velocity_and_torque:
        raise ConfigError(
            "use_velocity_and_torque must match across follower and leader "
            f"(follower={follower.use_velocity_and_torque}, "
            f"leader={leader.use_velocity_and_torque}); "
            "a mismatch is a runtime KeyError in build_dataset_frame (01 FR-SYS-012)"
        )


@dataclass(frozen=True)
class BimanualSessionConfig:
    """A bimanual session: two follower arms and one leader.

    Construction validates that both sides are set and the velocity-torque switch
    is one value across both arms and the leader (01 FR-SYS-012/013).

    Attributes:
        left: The left follower config.
        right: The right follower config.
        leader: The teleoperator config.
    """

    left: FollowerConfig
    right: FollowerConfig
    leader: LeaderConfig

    def __post_init__(self) -> None:
        """Reject wrong sides or a velocity-torque switch that is not uniform."""
        if self.left.side is not Side.LEFT or self.right.side is not Side.RIGHT:
            raise ConfigError(
                "bimanual session needs left.side=LEFT and right.side=RIGHT "
                f"(got {self.left.side}, {self.right.side})"
            )
        validate_teleop_pairing(self.left, self.leader)
        validate_teleop_pairing(self.right, self.leader)
