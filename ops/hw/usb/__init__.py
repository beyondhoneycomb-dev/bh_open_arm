"""USB topology / RTT / HOL measurement harness (WP-0B-06).

The M-1 hardware-side measurement (`15` §2.10 M-1, NFR-PRF-046): sweep the CAN
control frequency to find each arm's `f_max_can` with an RTT distribution, record
the USB topology and per-arm bus statistics, count the frames consumed per cycle
(`PG-CAN-001`), and characterise single-WebSocket HOL blocking. The measurement's
hard precondition (`15` §2.10 M-1) is that a single process holds the `WP-0B-01`
`flock` on every channel — a measurement without it is void and its artifact is
refused.

The surface:

- `require_lock_for_measurement` / `publish_artifact` — the precondition gate and the
  lock-guarded publish path. Publishing without the flock held is refused and writes
  nothing; a published artifact carries `lock_held=true` evidence.
- `parse_topology` — `lsusb -t` into a root-hub/controller tree with adapter
  membership and the HS-USB-2.0 (480M) link-speed check.
- `compute_distribution` — RTT percentiles *with* a histogram (summary-only is
  forbidden).
- `compute_fmax` — per-arm `f_max_can` by the tool's 0.95 achieved-rate rule.
- `record_frames_per_cycle` — frames-consumed-per-cycle and the `PG-CAN-001` verdict.
- `parse_bus_stats` — `ip -s -d link show` error counters and restarts.
- `build_hol_report` — the structural HOL characterisation.
- `run_live_measurement` / `real_measurement_available` — the deferred live path,
  which shells out to real tools and is skipped where no adapter exists.
- `reverify_from_fixture` — re-runs the parse chain against real captures the moment
  a fixture directory is supplied.

This package shells out to `lsusb` / `ip` / `motor_sampling_check`; it imports no CAN
library, keeping the measurement code off the robot stack.
"""

from __future__ import annotations

from ops.hw.usb.artifact import (
    ARTIFACT_SCHEMA,
    ArtifactSource,
    MeasurementArtifact,
    publish_artifact,
)
from ops.hw.usb.distribution import (
    Distribution,
    HistogramBin,
    compute_distribution,
    percentile,
)
from ops.hw.usb.fmax import FmaxResult, SweepRun, compute_fmax
from ops.hw.usb.frames import FramesPerCycle, FrameVerdict, record_frames_per_cycle
from ops.hw.usb.hol import HolReport, build_hol_report
from ops.hw.usb.iplink import CanBusStats, parse_bus_stats
from ops.hw.usb.measure import (
    DEFAULT_SWEEP_HZ,
    real_measurement_available,
    run_live_measurement,
)
from ops.hw.usb.precondition import (
    LockHeldEvidence,
    MeasurementRefusedError,
    require_lock_for_measurement,
)
from ops.hw.usb.reverify import ReverifyResult, fixture_dir_from_env, reverify_from_fixture
from ops.hw.usb.sampling import SweepRunSamples, parse_run, parse_sweep
from ops.hw.usb.topology import (
    AdapterLocation,
    TopologyReport,
    UsbBus,
    UsbNode,
    parse_topology,
)

__all__ = [
    "ARTIFACT_SCHEMA",
    "DEFAULT_SWEEP_HZ",
    "AdapterLocation",
    "ArtifactSource",
    "CanBusStats",
    "Distribution",
    "FmaxResult",
    "FramesPerCycle",
    "FrameVerdict",
    "HistogramBin",
    "HolReport",
    "LockHeldEvidence",
    "MeasurementArtifact",
    "MeasurementRefusedError",
    "ReverifyResult",
    "SweepRun",
    "SweepRunSamples",
    "TopologyReport",
    "UsbBus",
    "UsbNode",
    "build_hol_report",
    "compute_distribution",
    "compute_fmax",
    "fixture_dir_from_env",
    "parse_bus_stats",
    "parse_run",
    "parse_sweep",
    "parse_topology",
    "percentile",
    "publish_artifact",
    "real_measurement_available",
    "record_frames_per_cycle",
    "require_lock_for_measurement",
    "reverify_from_fixture",
    "run_live_measurement",
]
