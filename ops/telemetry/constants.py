"""Frozen telemetry constants from `14` FR-OPS-024 / FR-OPS-006 and `15` NFR-PRF-044.

Every value here is a decision drawn from a cited requirement, held in one place so a
tuning change moves a single line rather than a scattered set. The diagnostic window is
the one FR-OPS-024 names by number; the RSS slope threshold is the leak-detection knob of
NFR-PRF-044; the MCAP topics are the FR-OPS-006 timeseries channels.
"""

from __future__ import annotations

# FR-OPS-024: the crash report must carry the *preceding 30 s* of diagnostics. The window
# is the contract, not an implementation detail — the boundary test pins it exactly.
DIAGNOSTIC_WINDOW_S = 30.0

# A ring is bounded memory by definition. The window bounds it in time; this bounds it in
# count so a pathological burst rate cannot grow it without limit before eviction runs.
RING_MAX_SAMPLES = 100_000

# How often the control loop atomically republishes its crash context. SIGKILL is
# uncatchable, so the last context a supervisor can read is at most this old — the child
# writes nothing at death time, it only leaves behind its most recent flushed snapshot.
SPOOL_FLUSH_INTERVAL_S = 0.5

# Bytes per kibibyte — `/proc/<pid>/status` reports VmRSS in kB (which is KiB).
BYTES_PER_KIB = 1024

# NFR-PRF-044: a sustained positive RSS slope is a leak. The threshold is deliberately
# high so ordinary allocation churn does not read as a leak; a genuine unbounded growth
# fixture sits orders of magnitude above it.
RSS_LEAK_SLOPE_BYTES_PER_S = 500_000.0

# Least-squares slope over fewer points than this is noise, not a trend.
RSS_MIN_SAMPLES_FOR_SLOPE = 4

# Shell convention for a signal death: exit status 128 + signal number. Kept so the report
# can surface a conventional positive exit code alongside the raw signal.
SIGNAL_EXIT_OFFSET = 128

# The single file the control loop republishes and the crash reporter reads back.
CRASH_SPOOL_FILENAME = "crash_context.json"

# IPC protocol between the crash supervisor and the simulated control loop it spawns. Held
# here, not in the loop module, so importing the package never imports the `-m` entry point
# (which would collide with its own `runpy` execution).
CONTROL_LOOP_READY_PREFIX = "READY "
CONTROL_LOOP_OOM_COMMAND = "OOM"
CONTROL_LOOP_STOP_COMMAND = "STOP"

# FR-OPS-006 system-timeseries channels: joints, commands, diagnostics, CAN traces, video
# metadata. Held as topic strings so the MCAP writer and its readers share one spelling.
TOPIC_JOINTS = "/oa/joints"
TOPIC_COMMANDS = "/oa/commands"
TOPIC_DIAGNOSTICS = "/oa/diagnostics"
TOPIC_CAN_TRACE = "/oa/can_trace"
TOPIC_VIDEO_META = "/oa/video_meta"

MCAP_TOPICS = (
    TOPIC_JOINTS,
    TOPIC_COMMANDS,
    TOPIC_DIAGNOSTICS,
    TOPIC_CAN_TRACE,
    TOPIC_VIDEO_META,
)
