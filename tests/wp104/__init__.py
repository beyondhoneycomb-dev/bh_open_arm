"""WP-1-04 acceptance suite — the read-only measurement bench (PG-RT-001a / PG-CAN-001).

A small synthetic-load config so the one end-to-end run stays fast while still
exercising the full harness the WP-1-04 judgments consume; the judges, the f_max
arithmetic and the guards are tested on hand-built inputs and need no run at all.
"""

from __future__ import annotations

from sim.harness.conditions import MeasurementConfig

# A deliberately small config: a few hundred samples per state, enough for the rank
# test in the reused harness to resolve a biting load, small enough to keep the suite
# fast. Mirrors the WP-0C-06 fast config.
FAST_CONFIG = MeasurementConfig(
    target_hz=250.0,
    tick_count=150,
    warmup=30,
    self_overhead_iterations=500,
    sweep_frequencies_hz=(250.0,),
    sweep_tick_count=150,
    interleave_segment_len=12,
    interleave_repeats=16,
)

__all__ = ["FAST_CONFIG"]
