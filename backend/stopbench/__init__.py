"""WP-2A-06 — the stop-path latency regression bench: decompose PG-STOP-001 under Wave 2A.

WP-1-05 measures the deadman-release-to-CAN-stop total P99 with its mandatory
`clockProvenance`; this bench consumes that gate (`03` §5.7 names WP-2A-06 a downstream
consumer, not the owner) and adds the two things Wave 2A needs on top: it splits the one
interval into the four stages `02b` WP-2A-06 names — harness-event, transmit, scheduler,
CAN — so a regression can be attributed to a stage, and it confirms as a precondition that
the stop path holds no `disable_torque` (`04` NFR-MAN-002).

Reuse over re-implementation is the rule here, because two sources for one safety rule is
the worst outcome:

- the `disable_torque` absence is the WP-0A-01 scan (`backend.actuation.find_disable_torque`),
  run as a publish-gating precondition, not a second scanner;
- the `clockProvenance` refusal and the total P99 are WP-1-05's
  (`backend.torque_bringup.build_stop_latency_artifact`), never re-checked here;
- the full per-segment distributions are the WP-0C-06 histogram
  (`sim.harness.histogram.CycleTimeHistogram`), not a recomputed percentile triple.

What is genuinely new is the four-stage decomposition and the composition that wires the
precondition, the reused clock-gated total, and the decomposition into one artifact.

The real on-rig measurement needs torque-ON plus the kernel-clock instrumentation
`03` §5.7.0 demands, neither present on this host; it is deferred to `reverify` and never
asserted green (`THE ONE RULE`).

Public surface:

- `decompose` — the `StopPathSample`, its four segments, and the `StopPathDecomposition`.
- `precondition` — the reused `disable_torque` scan as an acceptance-③ refusal.
- `sources` — the capture-time adapter that reads the release boundary from the deadman
  lease (WP-2A-02, code reference) and takes the audit tick time (WP-2A-05) as a
  capture-file join, matching WP-2A-05's `06` §5.6 declaration that it is not imported.
- `bench` — the artifact assembly with its precondition and clock refusals.
- `reverify` — the deferred real-fixture re-verification hook.
"""

from __future__ import annotations

from backend.stopbench.bench import (
    REAL_CAPTURE_BASIS,
    SYNTHETIC_BASIS,
    build_stop_path_regression_artifact,
)
from backend.stopbench.constants import (
    FIXTURE_ENV_VAR,
    GATE,
    REFERENCE_TARGET_MS_UNCONFIRMED,
    WP_ID,
)
from backend.stopbench.decompose import (
    SEGMENT_ORDER,
    NonMonotonicSampleError,
    StopPathDecomposition,
    StopPathSample,
    StopPathSegment,
)
from backend.stopbench.precondition import (
    DEFAULT_STOP_PATH_ROOT,
    DisableTorqueOnStopPathError,
    NoDisableTorqueCheck,
    assert_no_disable_torque,
    check_no_disable_torque,
)
from backend.stopbench.reverify import (
    fixture_dir_from_env,
    parse_capture,
    reverify_from_fixture,
)
from backend.stopbench.sources import (
    release_boundary,
    sample_from_2a_sources,
)

__all__ = [
    "DEFAULT_STOP_PATH_ROOT",
    "FIXTURE_ENV_VAR",
    "GATE",
    "REAL_CAPTURE_BASIS",
    "REFERENCE_TARGET_MS_UNCONFIRMED",
    "SEGMENT_ORDER",
    "SYNTHETIC_BASIS",
    "WP_ID",
    "DisableTorqueOnStopPathError",
    "NoDisableTorqueCheck",
    "NonMonotonicSampleError",
    "StopPathDecomposition",
    "StopPathSample",
    "StopPathSegment",
    "assert_no_disable_torque",
    "build_stop_path_regression_artifact",
    "check_no_disable_torque",
    "fixture_dir_from_env",
    "parse_capture",
    "release_boundary",
    "reverify_from_fixture",
    "sample_from_2a_sources",
]
