"""WP-3B-10 — the teleop safety gate: heartbeat, workspace wall, velocity, pose sanity.

This package is the safety layer between the VR teleoperator source (`WP-3B-07`/`08`,
transformed and smoothed by `WP-3B-09`) and the actuation send path. It owns the slice
of the `05` §4.2 teleop state machine that link and pose safety turn on, and it holds
the safety-critical invariants that the demo must never fake green on:

- **Heartbeat, STALE = lost** (`FR-TEL-081`): no fresh OK frame within 100 ms on the
  server clock — or a STALE/INVALID validity — is a LINK_LOST, decelerated to a hold.
- **No auto-resume** (`FR-TEL-082`, `05` §4.2 #1/#3): a hold never resumes following on
  its own. The only exit is an explicit re-engage into ALIGNING, refused while the VR
  link is lost and refused while the deadman lease latch is held — the `WP-2A-02`
  re-arm is the superior handshake, and link recovery is not re-arming.
- **Command stream never stops** (`FR-TEL-079`): every tick emits a command, including
  the decelerate-then-hold, so the Damiao enable never drops.
- **Workspace wall** (`FR-TEL-036`): a base-frame keep-in box; an out-of-bounds EE
  target is projected onto the boundary.
- **EE velocity limit** (`FR-TEL-037`): the per-tick linear and angular pose delta is
  clamped to cartesian speed ceilings.
- **Pose sanity** (`FR-TEL-038`): a `det ≈ 0` or non-finite rotation is discarded and
  the last valid pose retained.
- **Startup RID9 check** (`FR-TEL-080`, `PG-RID-001`): the loop period must beat the
  Damiao comm-loss timeout or torque-on is blocked.

It consumes `CTR-TEL@v1` (`TeleopSample`, `TeleopValidity`) and the `WP-2A-02` deadman
lease latch by reference, redefining neither.
"""

from __future__ import annotations

from backend.teleop.safety_gate.constants import (
    DEFAULT_HEARTBEAT_TIMEOUT_MS,
    DEFAULT_LINK_LOST_DECEL_M_S2,
    DEFAULT_MAX_ANGULAR_VEL_RAD_S,
    DEFAULT_MAX_LINEAR_VEL_M_S,
    ROTATION_DET_ABS_TOL,
    TREAT_STALE_AS_LOST,
)
from backend.teleop.safety_gate.gate import (
    GateOutput,
    LeaseLatchView,
    TeleopSafetyGate,
    deadman_lease_view,
)
from backend.teleop.safety_gate.heartbeat import LinkHealth, LinkHeartbeat
from backend.teleop.safety_gate.pose import EEPose, Matrix3, Vector3
from backend.teleop.safety_gate.sanity import PoseSanityFilter, SanityResult, is_pose_sane
from backend.teleop.safety_gate.startup import (
    LoopPeriodError,
    Rid9CheckResult,
    Rid9Verdict,
    evaluate_loop_period,
    verify_loop_period_under_rid9_timeout,
)
from backend.teleop.safety_gate.states import (
    ForbiddenTransitionError,
    LinkNotLiveError,
    RearmRequiredError,
    TeleopLinkState,
)
from backend.teleop.safety_gate.velocity import EEVelocityLimiter, VelocityLimitResult
from backend.teleop.safety_gate.workspace import WallProjection, WorkspaceBox

__all__ = [
    "DEFAULT_HEARTBEAT_TIMEOUT_MS",
    "DEFAULT_LINK_LOST_DECEL_M_S2",
    "DEFAULT_MAX_ANGULAR_VEL_RAD_S",
    "DEFAULT_MAX_LINEAR_VEL_M_S",
    "ROTATION_DET_ABS_TOL",
    "TREAT_STALE_AS_LOST",
    "EEPose",
    "EEVelocityLimiter",
    "ForbiddenTransitionError",
    "GateOutput",
    "LeaseLatchView",
    "LinkHealth",
    "LinkHeartbeat",
    "LinkNotLiveError",
    "LoopPeriodError",
    "Matrix3",
    "PoseSanityFilter",
    "RearmRequiredError",
    "Rid9CheckResult",
    "Rid9Verdict",
    "SanityResult",
    "TeleopLinkState",
    "TeleopSafetyGate",
    "Vector3",
    "VelocityLimitResult",
    "WallProjection",
    "WorkspaceBox",
    "deadman_lease_view",
    "evaluate_loop_period",
    "is_pose_sane",
    "verify_loop_period_under_rid9_timeout",
]
