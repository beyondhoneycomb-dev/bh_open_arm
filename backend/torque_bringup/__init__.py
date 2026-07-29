"""WP-1-05 — the guarded torque-ON bring-up, after PG-SAFE-001.

The one place torque comes on. Torque-ON is admitted only against two independent
authorizations — `backend.preflight`'s five live preconditions and this package's manifest of
gate verdicts (PG-SAFE-001 PASS with its hash declared, PG-RID-001 PASS, the WP-1-02 zero
residual, the WP-1-03 zero-bypass gateway) — and then engages a present-pose hold under 0xFC
on the fitted motors only, never an arbitrary target and never a fixed eight. A SAFE_HOLD is
a gravity-comp hold (kp > 0), not torque 0, because a QDD joint has no brake (`01` §4.1,
`12` NFR-SAF-009).

This package owns the offline half of that: the guarded engage and its reversal, the
precondition manifest gate, the SAFE_HOLD impl check, the refusal that the stop path cuts no
torque, and the lease-expiry-forces-a-hold and hold-maintenance demonstrations over the
actuation spine. The hardware half — the real 0xFC on real motors, the power-cycle zero
re-verify, and the hard-E-Stop drop — is deferred to a real fixture and re-run by
`reverify.reverify_from_fixture` (`02a` §4.1); it is never asserted green here, because a
human trusts these gates before powering a 40 Nm brakeless arm.

The release-to-CAN-stop latency is not one of this WP's measurements. `stop_latency` states
the clock constraint that puts it out of reach; its builder ships from here as the single
definition `backend.loadtest.stop_path` consumes.
"""

from __future__ import annotations

from backend.torque_bringup.estop import (
    HardEStopRecord,
    find_post_estop_recovery,
    observe_hard_estop,
)
from backend.torque_bringup.hold import (
    HoldMaintenanceReport,
    LeaseExpiryReport,
    SafeHoldViolationError,
    assert_safe_hold,
    verify_hold_maintenance,
    verify_lease_expiry,
)
from backend.torque_bringup.preconditions import (
    GatePass,
    GatewayBypassPrecondition,
    TorqueOnManifest,
    TorqueOnRefusedError,
    ZeroResidualPrecondition,
    assert_torque_on_allowed,
)
from backend.torque_bringup.reverify import (
    RealVerification,
    fixture_dir_from_env,
    reverify_from_fixture,
)
from backend.torque_bringup.sequence import (
    EngageResult,
    FittedMotorMismatchError,
    GuardedTorqueOn,
    TorqueDisengageRefusedError,
    TorqueEngageBus,
    TorqueEngageSequenceError,
    assert_pose_covers_fitted_motors,
    assert_targets_are_present_pose,
    build_present_pose_hold,
)
from backend.torque_bringup.stop_latency import (
    ClockProvenance,
    StopLatencyArtifactRefusedError,
    build_stop_latency_artifact,
)
from backend.torque_bringup.stop_path import (
    TORQUE_BRINGUP_ROOT,
    TorqueCutOnStopPathError,
    assert_stop_path_cuts_no_torque,
    find_torque_cut_on_stop_path,
)

__all__ = [
    "TORQUE_BRINGUP_ROOT",
    "ClockProvenance",
    "EngageResult",
    "FittedMotorMismatchError",
    "GatePass",
    "GatewayBypassPrecondition",
    "GuardedTorqueOn",
    "HardEStopRecord",
    "HoldMaintenanceReport",
    "LeaseExpiryReport",
    "RealVerification",
    "SafeHoldViolationError",
    "StopLatencyArtifactRefusedError",
    "TorqueCutOnStopPathError",
    "TorqueDisengageRefusedError",
    "TorqueEngageBus",
    "TorqueEngageSequenceError",
    "TorqueOnManifest",
    "TorqueOnRefusedError",
    "ZeroResidualPrecondition",
    "assert_pose_covers_fitted_motors",
    "assert_safe_hold",
    "assert_stop_path_cuts_no_torque",
    "assert_targets_are_present_pose",
    "assert_torque_on_allowed",
    "build_present_pose_hold",
    "build_stop_latency_artifact",
    "find_post_estop_recovery",
    "find_torque_cut_on_stop_path",
    "fixture_dir_from_env",
    "observe_hard_estop",
    "reverify_from_fixture",
    "verify_hold_maintenance",
    "verify_lease_expiry",
]
