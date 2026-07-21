"""WP-OPS-05 — structured logging, MCAP timeseries, and the crash watchdog.

Owned tree: `ops/telemetry/**` (EXCLUSIVE). The package implements four things the plan groups
together because they share one job — explaining what the backend was doing when it stopped:

- a structured logger feeding a preceding-30 s diagnostic ring buffer (`14` FR-OPS-024);
- an MCAP system-timeseries writer that runs in a separate process (`14` FR-OPS-006,
  `15` NFR-PRF-038), with no rosbag2 dependency;
- a crash reporter that assembles the four required fields after an uncatchable death;
- the F23 (re-connect zeroing) and F24 (`use_velocity_and_torque`) session guards, plus the
  per-process RSS-slope leak monitor (`15` NFR-PRF-044).

`12` NFR-SAF-009 is embedded throughout: the watchdog cannot prevent a drop, only delay one.
`drop_disclaimer` holds that fact as a constant and proves it is present in the contract doc.
"""

from __future__ import annotations

from ops.telemetry.connect_guard import ZeroingConnectGuard, ZeroingDestroyedError, mode_transition
from ops.telemetry.connect_staticcheck import find_connect_in_mode_transition
from ops.telemetry.crash_report import CrashReport
from ops.telemetry.crash_reporter import SupervisedLoop, decode_exit, report_from_return_code
from ops.telemetry.drop_disclaimer import (
    DROP_DISCLAIMER,
    REQUIRED_DISCLAIMER_PHRASE,
    assert_disclaimer_present,
    doc_has_disclaimer,
)
from ops.telemetry.mcap_writer import McapWriterProcess, load_mcap
from ops.telemetry.ring_buffer import DiagnosticRingBuffer, RingSink
from ops.telemetry.ros_staticcheck import find_forbidden_ros_imports
from ops.telemetry.rss_monitor import RssSlopeMonitor, read_rss_bytes
from ops.telemetry.state_transition import StateTransitionLog
from ops.telemetry.structured_log import StructuredLogger
from ops.telemetry.velocity_torque import (
    TorqueDataLossError,
    assert_velocity_and_torque_at_session_start,
    check_velocity_and_torque,
)

__all__ = [
    "DROP_DISCLAIMER",
    "REQUIRED_DISCLAIMER_PHRASE",
    "CrashReport",
    "DiagnosticRingBuffer",
    "McapWriterProcess",
    "RingSink",
    "RssSlopeMonitor",
    "StateTransitionLog",
    "StructuredLogger",
    "SupervisedLoop",
    "TorqueDataLossError",
    "ZeroingConnectGuard",
    "ZeroingDestroyedError",
    "assert_disclaimer_present",
    "assert_velocity_and_torque_at_session_start",
    "check_velocity_and_torque",
    "decode_exit",
    "doc_has_disclaimer",
    "find_connect_in_mode_transition",
    "find_forbidden_ros_imports",
    "load_mcap",
    "mode_transition",
    "read_rss_bytes",
    "report_from_return_code",
]
