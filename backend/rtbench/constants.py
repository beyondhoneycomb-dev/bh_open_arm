"""Named constants for the WP-1-04 read-only measurement bench.

Every value here is a spec-given threshold or band, not a measured target: the
main-path band and its overrun budget come from `15` §2.10 / NFR-PRF-040, the
frequency-headroom and actual-vs-target ratios from `15` NFR-PRF-004, and the
frames-per-cycle counts from `15` §2.1. They are the pass lines the measurement is
judged against, not numbers the measurement produces — which is why they carry no
`registry/build/evidence/` anchor (CI-11 anchors *produced* targets, not spec
constants).
"""

from __future__ import annotations

# `15` §2.10 condition 4 / acceptance ⑤: the main control-path band the overrun
# judgment is rendered over. Below 30 Hz is not a real-time control regime and above
# 250 Hz is past the single-arm frame budget (`01` NFR-SYS-002, ~625 Hz pattern B).
MAIN_PATH_BAND_LOW_HZ = 30.0
MAIN_PATH_BAND_HIGH_HZ = 250.0

# `15` NFR-PRF-040: a main-path pass is an overrun rate at or below 0.1%.
MAIN_PATH_OVERRUN_BUDGET = 1e-3

# `15` NFR-PRF-004: a later target frequency must not exceed f_max x 0.8, and a cycle
# is on-time when its actual frequency is at least 0.95 x target.
TARGET_FREQ_HEADROOM = 0.8
ACTUAL_HZ_PASS_RATIO = 0.95

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
