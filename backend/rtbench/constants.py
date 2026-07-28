"""Named constants for the WP-1-04 read-only measurement bench.

Two kinds of value live here, and they carry no `registry/build/evidence/` anchor for
the same reason: neither is a number the measurement produces (CI-11 anchors *produced*
targets, not spec constants).

The first kind is a spec-given band or budget the measurement is judged against — the
main-path band and its overrun budget from `15` §2.10 / NFR-PRF-040, the frequency
headroom from `15` NFR-PRF-004, the frames-per-cycle counts from `15` §2.1.

The second is the vocabulary of what gets published: which distribution figures the
artifact must carry and which quantity a verdict was rendered on. NORM-008 makes that a
requirement rather than a formatting choice, so it is named rather than spelled inline.
"""

from __future__ import annotations

# `15` §2.10 condition 4 / acceptance ⑤: the main control-path band the overrun
# judgment is rendered over. Below 30 Hz is not a real-time control regime and above
# 250 Hz is past the single-arm frame budget (`01` NFR-SYS-002, ~625 Hz pattern B).
MAIN_PATH_BAND_LOW_HZ = 30.0
MAIN_PATH_BAND_HIGH_HZ = 250.0

# `15` NFR-PRF-040: a main-path pass is an overrun rate at or below 0.1%.
MAIN_PATH_OVERRUN_BUDGET = 1e-3

# `15` NFR-PRF-004's x 0.8. NORM-008 keeps the number and drops the enforcement: the
# artifact publishes `f_max x 0.8` as a figure a reader judges once the real measurement
# exists, and nothing refuses a target for exceeding it.
TARGET_FREQ_HEADROOM = 0.8

# NORM-008 names the four figures the cycle-time distribution must surface: median,
# 95th, 99th, maximum. Spelled as the keys `CycleTimeHistogram.summary()` produces, in
# ascending order, so a missing one is caught rather than silently dropped.
REPORTED_DISTRIBUTION_KEYS = ("p50", "p95", "p99", "max")
MEDIAN_DISTRIBUTION_KEY = "p50"

# The quantity `PG-RT-001a` is decided on. Named in the verdict record so the artifact
# states in itself that the gate reads overrun, never a frequency (NORM-008).
OVERRUN_RATE_CRITERION = "overrun_rate"

# Carried beside every cycle-time figure, so a reader cannot mistake a produced number
# for a confirmed pass line (NORM-008; same stance as the WP-5-05 latency measurement).
CYCLE_TIME_NOTE = (
    "measurement only: NORM-008 rules that no frequency is a pass/fail criterion, so the "
    "distribution and the achieved rate are surfaced and judged by a reader, not by code"
)

# `15` §2.1: LeRobot's default loop is pattern B at 32 frames/cycle; pattern A skips
# the full observation read and runs 16. These are the two counts `PG-CAN-001` reads.
PATTERN_B_FRAMES_PER_CYCLE = 32
PATTERN_A_FRAMES_PER_CYCLE = 16

# `03` §5.1a gate ids. `a` is the provisional synthetic-load verdict this WP renders;
# `b` (Wave 3C, WP-3C-02) is the canonical real-camera verdict that supersedes it.
PROVISIONAL_GATE = "PG-RT-001a"
FINAL_GATE = "PG-RT-001b"
FRAME_GATE = "PG-CAN-001"

# `06` CI-11c: anything derived from the provisional `a` must carry this trigger so
# confirming `b` forces re-derivation and the synthetic figure cannot survive as final.
REQUIRED_STALE_TRIGGER = f"{FINAL_GATE}:PASS"

# The two gate states this WP's verdicts use, spelled exactly as the registry's gate
# state machine names them (`06` §5, registry/checks/wp.py).
GATE_STATE_PASS = "PASS"
GATE_STATE_RETRY_WITH_VARIANT = "RETRY_WITH_VARIANT"

# The synthetic-load basis label for every provisional figure this WP publishes.
SYNTHETIC_BASIS = "synthetic-gil-load"
