"""WP-1-04 — the read-only measurement bench: judge PG-RT-001a / PG-CAN-001, derive f_max.

This package is the `AI-on-HW` half of Wave 1 (`03` §5.1a): it binds the rig once with
torque OFF, holds the CAN channel lock, and judges the control loop the `WP-0C-06`
synthetic harness measured. It renders the provisional `PG-RT-001a` verdict on the swept
overrun rates, judges `PG-CAN-001` frames-per-cycle, and computes
`f_max = min(f_max_can, f_max_python)` and the `x 0.8` figure derived from it.

The judgment *basis* is the synthetic GIL load, which runs on this host; every figure
it publishes is therefore provisional and names `PG-RT-001b` (Wave 3C) as the gate
that supersedes it. The real-CAN inputs — the on-hardware sweep, the real `candump`
frame count, and `WP-0B-06`'s `f_max_can` — are deferred to the re-verification hook in
`reverify`, never faked.

No frequency in this package decides a pass or a fail. NORM-008 rules that a frequency is
measured and surfaced and judged later by a reader, so `f_max x 0.8` is a published figure
that refuses nothing, the 30-250 Hz main-path band is a label on each point rather than a
filter on the verdict, and the cycle-time distribution is published beside them.
`staticcheck` proves mechanically that no frequency reaches a verdict here — as a bar that
aborts, a gate state, a filter over the measured points, or a published permit; what no
single expression states is held by the behavioural lock in
`tests/wp104/test_no_frequency_gate.py`.

Public surface:

- `judge` — the `PG-RT-001a` verdict and its frozen retry escalation.
- `frame_count` — the `PG-CAN-001` verdict, provenance-aware.
- `fmax` — `min(f_max_can, f_max_python)` and the `x 0.8` figure derived from it.
- `cycle_time` — the operating point's distribution, overrun share and achieved rate.
- `session` — the single-connect, torque-OFF, lock-held measurement session.
- `publish` — artifact assembly with its publication-refusal guards.
- `reverify` — the deferred real-CAN re-verification hook.
- `staticcheck` — the scan proving no frequency value drives a verdict.
"""

from __future__ import annotations

from backend.rtbench.cycle_time import CycleTimeMeasurement, measure_cycle_time
from backend.rtbench.fmax import FMax, compute_fmax
from backend.rtbench.frame_count import (
    FrameCountSource,
    FrameCountStatus,
    PgCan001Verdict,
    judge_pg_can_001,
)
from backend.rtbench.judge import (
    FORCED_VARIANT_ESCALATION,
    BandPoint,
    PgRt001aVerdict,
    Variant,
    band_points_from_sweep,
    judge_pg_rt_001a,
)
from backend.rtbench.publish import (
    MeasurementArtifactRefusedError,
    build_measurement_artifact,
)
from backend.rtbench.reverify import (
    FIXTURE_ENV_VAR,
    RealVerification,
    fixture_dir_from_env,
    reverify_from_fixture,
)
from backend.rtbench.rig import RigReadonlyConnect, RigTorqueProbe
from backend.rtbench.session import (
    NotConnectedError,
    ReadOnlyMeasurementSession,
    RepeatedConnectError,
    TorqueEngagedError,
    TorqueProbe,
    TorqueState,
)
from backend.rtbench.staticcheck import (
    FrequencyVerdictSite,
    scan_frequency_verdicts,
)

__all__ = [
    "FIXTURE_ENV_VAR",
    "FORCED_VARIANT_ESCALATION",
    "BandPoint",
    "CycleTimeMeasurement",
    "FMax",
    "FrameCountSource",
    "FrameCountStatus",
    "FrequencyVerdictSite",
    "MeasurementArtifactRefusedError",
    "NotConnectedError",
    "PgCan001Verdict",
    "PgRt001aVerdict",
    "ReadOnlyMeasurementSession",
    "RealVerification",
    "RepeatedConnectError",
    "RigReadonlyConnect",
    "RigTorqueProbe",
    "TorqueEngagedError",
    "TorqueProbe",
    "TorqueState",
    "Variant",
    "band_points_from_sweep",
    "build_measurement_artifact",
    "compute_fmax",
    "fixture_dir_from_env",
    "judge_pg_can_001",
    "judge_pg_rt_001a",
    "measure_cycle_time",
    "reverify_from_fixture",
    "scan_frequency_verdicts",
]
