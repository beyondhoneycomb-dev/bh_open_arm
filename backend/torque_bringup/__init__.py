"""WP-1-05 — the guarded torque-ON bring-up, after PG-SAFE-001.

The one place torque comes on. `02a` §7 admits torque-ON only after four preconditions —
PG-SAFE-001 PASS (hash declared), PG-RID-001 PASS, the WP-1-02 zero residual, and the
WP-1-03 zero-bypass gateway — and then engages a present-pose hold under 0xFC, never an
arbitrary target. A SAFE_HOLD is a gravity-comp hold (kp > 0), not torque 0, because a QDD
joint has no brake (`01` §4.1, `12` NFR-SAF-009).

This package owns the offline half of that: the guarded torque-ON sequence and its ordering,
the precondition manifest gate, the SAFE_HOLD impl check, the lease-expiry-forces-a-hold and
hold-maintenance demonstrations over the actuation spine, and the PG-STOP-001 evidence with
its mandatory clockProvenance. The hardware half — the real 0xFC on real motors, the real
release-to-CAN-stop P99, the power-cycle zero re-verify, and the hard-E-Stop drop — is
deferred to a real fixture and re-run by `reverify.reverify_from_fixture` (`02a` §4.1); it is
never asserted green here, because a human trusts these gates before powering a 40 Nm
brakeless arm.
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
    GuardedTorqueOn,
    TorqueEngageBus,
    TorqueEngageSequenceError,
    build_present_pose_hold,
)
from backend.torque_bringup.stop_latency import (
    ClockProvenance,
    StopLatencyArtifactRefusedError,
    build_stop_latency_artifact,
)

__all__ = [
    "ClockProvenance",
    "EngageResult",
    "GatePass",
    "GatewayBypassPrecondition",
    "GuardedTorqueOn",
    "HardEStopRecord",
    "HoldMaintenanceReport",
    "LeaseExpiryReport",
    "RealVerification",
    "SafeHoldViolationError",
    "StopLatencyArtifactRefusedError",
    "TorqueEngageBus",
    "TorqueEngageSequenceError",
    "TorqueOnManifest",
    "TorqueOnRefusedError",
    "ZeroResidualPrecondition",
    "assert_safe_hold",
    "assert_torque_on_allowed",
    "build_present_pose_hold",
    "build_stop_latency_artifact",
    "find_post_estop_recovery",
    "fixture_dir_from_env",
    "observe_hard_estop",
    "reverify_from_fixture",
    "verify_hold_maintenance",
    "verify_lease_expiry",
]
