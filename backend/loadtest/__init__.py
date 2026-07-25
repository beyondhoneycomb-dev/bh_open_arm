"""WP-5-05 phase-1 — the single-WS load test (HOL blocking, multi-client).

This package is the synthetic-load half of WP-5-05 (`02c` §4.5). It proves, on a
deterministic model of the one WebSocket (U-4), the things phase-1 is allowed to
conclude without hardware:

  * `CG-5-05a` a control-class round-trip latency measurement is produced under max
    load — no pass line is set (`NFR-GUI-004`/`NFR-GUI-005` are decision-needed).
  * `CG-5-05b` at saturation the camera degrades first while lease/command/telemetry
    are protected — an order, not a number, so it is decidable now.
  * `CG-5-05c` the WS publish rate obeys 30 Hz default / 60 Hz cap with no
    control-loop full-rate leak.
  * `CG-5-05d` a WS delay → missed renewal → lease expiry → scheduler auto-hold.
  * `CG-5-05e` the report states the residual risk verbatim.
  * `CG-5-05f` a soft-estop-path P99 is measured and shown against the `[unconfirmed]`
    20 ms reference; the authoritative PG-STOP-001 is deferred (no HW).

It reuses rather than forks: the frame priorities, backpressure signal and protected
set come from `CTR-WS@v1` (`contracts.ws`); camera load is sized from the `06` §2.9
budget (`backend.camera`); the auto-hold path runs the real `LeaseManager`,
`DeadmanController` and `decide` (`backend.actuation` / `backend.deadman`); the stop
reference and its refusal come from `backend.torque_bringup`.
"""

from __future__ import annotations

from backend.loadtest.backpressure import (
    BackpressurePolicyVerdict,
    verify_backpressure_policy,
)
from backend.loadtest.harness import (
    ClassResult,
    LoadProfile,
    LoadRun,
    run_load,
)
from backend.loadtest.hol_judge import (
    OrderingJudgment,
    OrderingVerdict,
    RoundTripMeasurement,
    judge_ordering,
    measure_roundtrip,
)
from backend.loadtest.lease_delay import (
    LeaseDelayResult,
    inject_ws_delay,
)
from backend.loadtest.publish_rate import (
    PublishRateResolution,
    PublishRateVerdict,
    resolve_publish_rate,
    verify_publish_rate_policy,
)
from backend.loadtest.report import (
    LoadTestReport,
    LoadTestReportRefusedError,
    build_load_test_report,
)
from backend.loadtest.stop_path import (
    StopPathComparison,
    deferred_real_stop_latency,
    measure_soft_estop_path,
)

__all__ = [
    "BackpressurePolicyVerdict",
    "ClassResult",
    "LeaseDelayResult",
    "LoadProfile",
    "LoadRun",
    "LoadTestReport",
    "LoadTestReportRefusedError",
    "OrderingJudgment",
    "OrderingVerdict",
    "PublishRateResolution",
    "PublishRateVerdict",
    "RoundTripMeasurement",
    "StopPathComparison",
    "build_load_test_report",
    "deferred_real_stop_latency",
    "inject_ws_delay",
    "judge_ordering",
    "measure_roundtrip",
    "measure_soft_estop_path",
    "resolve_publish_rate",
    "run_load",
    "verify_backpressure_policy",
    "verify_publish_rate_policy",
]
