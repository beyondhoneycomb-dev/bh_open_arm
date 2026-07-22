"""OpenArm follower plugin configs (CTR-PLUG@v1, 01 FR-SYS-014).

LeRobot is extended through its third-party plugin mechanism — a `lerobot_robot_*`
distribution whose module registers `RobotConfig` choices — never by forking it
(01 FR-SYS-003/014). These configs register the hardware OpenArm follower under
choice names distinct from LeRobot's built-in `openarm_follower` /
`bi_openarm_follower` hardcoded branch (16 D-1), so selecting our subclass resolves
through the third-party fallback in `make_robot_from_config` (robots/utils.py
else-branch) and edits zero hardcoded lines.

The value contract each config carries — `side` required with no usable default,
`use_velocity_and_torque` matched follower/leader — is not restated here: it is the
frozen CTR-PLUG@v1 config validation (`contracts.plugin.config`), reused so the
plugin and the frozen contract cannot disagree. The concrete follower device classes
(`OaOpenArmFollower`, `BiOaOpenArmFollower`) are added to this package by WP-1-02
(`openarm_follower_oa.py`) under the sequential ownership handover; this file owns
only their configs.
"""

from __future__ import annotations

from dataclasses import dataclass

from lerobot.robots.config import RobotConfig

from contracts.plugin.config import FollowerConfig, Side

# The LeRobot choice names this plugin registers. They are CLI/config tokens
# (`--robot.type=oa_openarm_follower`), not source edits to LeRobot, and are
# deliberately distinct from LeRobot's built-in `openarm_follower` /
# `bi_openarm_follower` (16 D-1) so resolution goes through the third-party fallback.
OA_FOLLOWER_TYPE = "oa_openarm_follower"
BI_OA_FOLLOWER_TYPE = "bi_oa_openarm_follower"


@RobotConfig.register_subclass(OA_FOLLOWER_TYPE)
@dataclass(kw_only=True)
class OaOpenArmFollowerConfig(RobotConfig):
    """Config for one hardware OpenArm follower arm.

    `side` has no usable default: LeRobot's default `joint_limits` of +/-5 degrees
    makes the arm effectively inert (01 FR-SYS-013), so the value must be stated.
    Validation is delegated to the frozen CTR-PLUG@v1 config contract so the two
    cannot drift.

    Attributes:
        side: Which arm this follower drives; required (no usable default).
        use_velocity_and_torque: Whether velocity/torque channels are recorded
            (01 FR-SYS-012); must match the paired leader.
    """

    side: Side | None = None
    use_velocity_and_torque: bool = False

    def __post_init__(self) -> None:
        """Validate against the frozen follower contract, then the base config."""
        super().__post_init__()
        # Constructing the frozen FollowerConfig runs its validation (a None side is
        # refused there with the FR-SYS-013 rationale); reusing it keeps one source
        # of truth for what a follower config must satisfy.
        FollowerConfig(side=self.side, use_velocity_and_torque=self.use_velocity_and_torque)


@RobotConfig.register_subclass(BI_OA_FOLLOWER_TYPE)
@dataclass(kw_only=True)
class BiOaOpenArmFollowerConfig(RobotConfig):
    """Config for the bimanual hardware OpenArm follower (both arms, 01 §4.2 T1).

    Both arms share one `use_velocity_and_torque` switch (01 FR-SYS-012); the sides
    are fixed left+right, so no per-arm `side` is stated here.

    Attributes:
        use_velocity_and_torque: Whether velocity/torque channels are recorded;
            applied to both arms and must match the paired leader.
    """

    use_velocity_and_torque: bool = False
