"""WP-0C-06 — the synthetic GIL-load harness, the PG-RT-001a basis (`03` §5.1a).

This package reproduces the shape of `15` §2.10 condition 4 (five-stream grab +
lossless-PNG write + dataset write + WS serialization in one process) as a synthetic
workload with no real cameras, measures how it inflates a victim control loop's cycle
time, and publishes the full distributions plus the derived basis metrics: the GIL
contribution, the proof the load bites, the RT-promotion gain, and the harness
self-overhead. It pins no numeric verdict — the `f_max_python` it derives is
provisional, judged later by `WP-1-04` and superseded by `PG-RT-001b` (`WP-3C-02`).

The harness never connects a rig (`connect()` call count is 0); real-rig binding is
`WP-1-04`. It consumes the `WP-0C-05` dummy as its bench device.
"""

from __future__ import annotations

from sim.harness.artifact import ArtifactRefusedError, build_artifact, write_artifact
from sim.harness.conditions import MeasurementConfig
from sim.harness.harness import HarnessResult, run_harness
from sim.harness.load_profile import InvalidLoadProfileError, LoadProfile

__all__ = [
    "ArtifactRefusedError",
    "HarnessResult",
    "InvalidLoadProfileError",
    "LoadProfile",
    "MeasurementConfig",
    "build_artifact",
    "run_harness",
    "write_artifact",
]
