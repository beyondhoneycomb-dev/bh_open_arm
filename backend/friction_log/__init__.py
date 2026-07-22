"""WP-2B-05 — the 1 kHz logging harness, a no-transmit tap (SAFETY-CRITICAL).

The friction-identification wave needs pos/vel/tau at the tick rate, and it must collect
it without ever becoming a second CAN writer: one writer holds the bus for the whole
torque-ON window (I-1), and a logger that transmits drops a brakeless arm. Two taps satisfy
that, and neither drives the bus:

- **Pattern A — `SchedulerLogTap`.** Rides the one Wave-1 scheduler: it is the scheduler's
  `TraceSink`, so pos/vel/tau are emitted from inside each tick, at the tick rate, without
  forking the scheduler and without any CAN handle.
- **Pattern B — `open_rx_only_socket`.** A separate read-only SocketCAN socket whose write
  half is shut at the OS; it receives the frames already on the bus and transmits nothing.

`staticcheck.scan_tree` is the load-bearing guarantee: zero CAN transmit symbols on the
logger path (①) and zero `get_observation` on the pattern-A tick path (⑥), checked over the
AST so the absence is real. `band` measures the achieved frequency/jitter here on synthetic
ticks but marks it provisional (the tick rate and `f_max_python` come from the
hardware-deferred `PG-RT-001a`); `reverify` carries the items that need a real bus (②③④⑤⑦).
"""

from __future__ import annotations

from backend.friction_log.band import (
    PATTERN_MANUAL_RX,
    PATTERN_SCHEDULER_TAP,
    AchievedBand,
    LoggingStats,
    achieved_band,
    logging_did_not_outrun_ticks,
    logging_stats,
)
from backend.friction_log.constants import BIMANUAL_JOINT_COUNT
from backend.friction_log.errors import HardwareDeferredError, LoggerTransmitError
from backend.friction_log.frame import LogFrame, frame_from_batch
from backend.friction_log.rx_tap import (
    CAN_FRAME_SIZE,
    decode_can_frame,
    encode_can_frame,
    open_rx_only_socket,
)
from backend.friction_log.scheduler_tap import SchedulerLogTap
from backend.friction_log.sink import LogSink, MemoryLogSink
from backend.friction_log.staticcheck import (
    RULE_CAN_TRANSMIT,
    RULE_GET_OBSERVATION,
    Finding,
    check_source,
    scan_tree,
)

__all__ = [
    "BIMANUAL_JOINT_COUNT",
    "CAN_FRAME_SIZE",
    "PATTERN_MANUAL_RX",
    "PATTERN_SCHEDULER_TAP",
    "RULE_CAN_TRANSMIT",
    "RULE_GET_OBSERVATION",
    "AchievedBand",
    "Finding",
    "HardwareDeferredError",
    "LogFrame",
    "LogSink",
    "LoggerTransmitError",
    "LoggingStats",
    "MemoryLogSink",
    "SchedulerLogTap",
    "achieved_band",
    "check_source",
    "decode_can_frame",
    "encode_can_frame",
    "frame_from_batch",
    "logging_did_not_outrun_ticks",
    "logging_stats",
    "open_rx_only_socket",
    "scan_tree",
]
