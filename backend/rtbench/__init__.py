"""WP-1-04 — the read-only measurement bench: judge PG-RT-001a / PG-CAN-001, derive f_max.

This package is the `AI-on-HW` half of Wave 1 (`03` §5.1a): it binds the rig once with
torque OFF, holds the CAN channel lock, and judges the control loop the `WP-0C-06`
synthetic harness measured. It renders the provisional `PG-RT-001a` verdict over the
main-path band, judges `PG-CAN-001` frames-per-cycle, and computes
`f_max = min(f_max_can, f_max_python)` with its `x 0.8` operating ceiling.

The judgment *basis* is the synthetic GIL load, which runs on this host; every figure
it publishes is therefore provisional and names `PG-RT-001b` (Wave 3C) as the gate
that supersedes it. The real-CAN inputs — the on-hardware sweep, the real `candump`
frame count, and `WP-0B-06`'s `f_max_can` — are deferred to the re-verification hook in
`reverify`, never faked.

Public surface:

- `judge` — the `PG-RT-001a` verdict and its frozen retry escalation.
- `frame_count` — the `PG-CAN-001` verdict, provenance-aware.
- `fmax` — `min(f_max_can, f_max_python)`, the `x 0.8` ceiling, the `0.95` on-time test.
- `session` — the single-connect, torque-OFF, lock-held measurement session.
- `publish` — artifact assembly with its publication-refusal guards.
- `reverify` — the deferred real-CAN re-verification hook.
"""

from __future__ import annotations

from backend.rtbench.fmax import (
    FMax,
    TargetExceedsFmaxError,
    compute_fmax,
    enforce_target_hz,
    meets_actual_hz,
)
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

__all__ = [
    "FIXTURE_ENV_VAR",
    "FORCED_VARIANT_ESCALATION",
    "BandPoint",
    "FMax",
    "FrameCountSource",
    "FrameCountStatus",
    "MeasurementArtifactRefusedError",
    "NotConnectedError",
    "PgCan001Verdict",
    "PgRt001aVerdict",
    "ReadOnlyMeasurementSession",
    "RealVerification",
    "RepeatedConnectError",
    "RigReadonlyConnect",
    "RigTorqueProbe",
    "TargetExceedsFmaxError",
    "TorqueEngagedError",
    "TorqueProbe",
    "TorqueState",
    "Variant",
    "band_points_from_sweep",
    "build_measurement_artifact",
    "compute_fmax",
    "enforce_target_hz",
    "fixture_dir_from_env",
    "judge_pg_can_001",
    "judge_pg_rt_001a",
    "meets_actual_hz",
    "reverify_from_fixture",
]
