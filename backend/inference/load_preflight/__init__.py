"""WP-4B-03 — inference load preflight (FR-INF-070/037/035/038/039/040, `02c` §2.3).

Three deliverables, one package:

- the load preflight (`LoadPreflight`) — the first-line gate that refuses a policy
  load on a checkpoint<->robot dimension mismatch, a left-gripper mirror violation,
  or an unset side, BEFORE the policy loads;
- the left-gripper sign-mirror validator (`mirror`) — the WRONG-SUCCESS defence;
- the v2 URDF limit loader (`limits`) — the one canon read once from
  `joint_limits.yaml` and injected into both `config_openarm_follower.joint_limits`
  (degrees) and the IK MJCF `jnt_range` (radians), the second via the committed
  `OrderedIkBuild` so the override lands before `Kinematics(...)`.

The command-wrap and velocity/jump-guard action-layer guards (`guards`) round out
the FR-INF-038/039/040 surface. Every heavy dependency (LeRobot policy configs,
mujoco/openarm_control) is imported lazily inside the functions that need it, so the
pure checks stay usable without the robot stack.
"""

from backend.inference.load_preflight.guards import (
    BIMANUAL_JOINT_MOTORS,
    JOINT_MOTORS,
    CommandWrapVerdict,
    MotionGuards,
    command_within_pmax,
    motor_vmax_rad_s,
    pmax_rad,
    resolve_velocity_limit,
)
from backend.inference.load_preflight.limits import (
    CANONICAL_YAML,
    CanonicalIkBuild,
    CanonicalLimitError,
    CanonicalLimits,
    TwoPlaceReport,
    apply_to_follower_config,
    build_canonical_ik_adapter,
    canonical_ik_jointlimits,
    config_joint_limits_deg,
    load_canonical_limits,
    verify_two_place_consistency,
)
from backend.inference.load_preflight.mirror import (
    GripperMirrorVerdict,
    check_gripper_mirror,
    check_gripper_mirror_from_limits,
    sign_mirror,
)
from backend.inference.load_preflight.preflight import LoadPreflight
from backend.inference.load_preflight.profiles import CheckpointProfile, RobotProfile
from backend.inference.load_preflight.verdict import (
    LoadRefusedError,
    LoadVerdict,
    Refusal,
    RefusalCode,
)

__all__ = [
    "BIMANUAL_JOINT_MOTORS",
    "CANONICAL_YAML",
    "JOINT_MOTORS",
    "CanonicalIkBuild",
    "CanonicalLimitError",
    "CanonicalLimits",
    "CheckpointProfile",
    "CommandWrapVerdict",
    "GripperMirrorVerdict",
    "LoadPreflight",
    "LoadRefusedError",
    "LoadVerdict",
    "MotionGuards",
    "Refusal",
    "RefusalCode",
    "RobotProfile",
    "TwoPlaceReport",
    "apply_to_follower_config",
    "build_canonical_ik_adapter",
    "canonical_ik_jointlimits",
    "check_gripper_mirror",
    "check_gripper_mirror_from_limits",
    "command_within_pmax",
    "config_joint_limits_deg",
    "load_canonical_limits",
    "motor_vmax_rad_s",
    "pmax_rad",
    "resolve_velocity_limit",
    "sign_mirror",
    "verify_two_place_consistency",
]
