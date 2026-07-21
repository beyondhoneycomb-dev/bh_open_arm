"""WP-0C-06 acceptance suite — the synthetic GIL-load harness (PG-RT-001a basis).

Shared repository paths and a small measurement config, so the timing tests run in a
few seconds while still collecting enough samples for the rank test to separate a
biting load from a no-load run.
"""

from __future__ import annotations

from pathlib import Path

from sim.harness.conditions import MeasurementConfig

REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS_DIR = REPO_ROOT / "sim" / "harness"

# A deliberately small config: a few hundred samples per state — enough for the
# rank test to resolve a biting load, small enough to keep the suite fast.
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

__all__ = [
    "FAST_CONFIG",
    "HARNESS_DIR",
    "REPO_ROOT",
]
