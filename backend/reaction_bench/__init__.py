"""WP-2C-06 — the reaction-time measurement bench: detection-confirm -> first reaction frame.

The reaction time the plan defines is one interval — detection confirmed (`WP-2C-04`) to the
first reaction MIT frame on the bus (`WP-2C-05`) — and this bench records its histogram and
splits it into the three stages the same-process reaction path has, so a regression can be
attributed to a stage and the negative branch's levers (retune the observer, shorten the
reaction path) become choosable. It renders no verdict: NFR-SAF-002/003/004 are all
decision-needed and the pass line is fixed after measurement by a regression gate
(`02b` WP-2C-06 acceptance 2).

Reuse over re-implementation is the rule here, because two sources for one safety rule is the
worst outcome:

- the `disable_torque` absence is the WP-0A-01 scan (`backend.actuation.find_disable_torque`),
  run as a publish-gating precondition, not a second scanner — the reaction is a continuous
  STOP_HOLD MIT frame, never a torque cut (`02b` WP-2C-05);
- the trusted-clock decision reuses WP-1-05's single-source `ALLOWED_CLOCK_METHODS` and its
  `ClockProvenance` record (`backend.reaction_bench.clock`), never a second trust set;
- the full per-segment distributions are the WP-0C-06 histogram
  (`sim.harness.histogram.CycleTimeHistogram`), not a recomputed percentile triple.

The real on-rig measurement needs torque-ON plus the kernel-clock instrumentation `03` §5.7.0
demands, neither present on this host; it is deferred to `reverify` and never asserted green
(`THE ONE RULE`).

Public surface:

- `latency` — the `ReactionSample`, its three segments, and the `ReactionTimeDecomposition`.
- `precondition` — the reused `disable_torque` scan as a publish-gating refusal.
- `clock` — the trusted-clock refusal reusing WP-1-05's single-source method set.
- `bench` — the artifact assembly with its precondition and clock refusals.
- `reverify` — the deferred real-fixture re-verification hook.
"""

from __future__ import annotations

from backend.reaction_bench.bench import (
    REAL_CAPTURE_BASIS,
    SYNTHETIC_BASIS,
    build_reaction_time_regression_artifact,
)
from backend.reaction_bench.clock import (
    ReactionLatencyRefusedError,
    assert_trusted_clock,
)
from backend.reaction_bench.constants import (
    FIXTURE_ENV_VAR,
    GATE,
    REFERENCE_NOTE,
    REFERENCE_TARGETS_DECISION_NEEDED,
    WP_ID,
)
from backend.reaction_bench.latency import (
    SEGMENT_ORDER,
    NonMonotonicSampleError,
    ReactionSample,
    ReactionSegment,
    ReactionTimeDecomposition,
)
from backend.reaction_bench.precondition import (
    DEFAULT_REACTION_PATH_ROOT,
    DisableTorqueOnReactionPathError,
    NoDisableTorqueCheck,
    assert_no_disable_torque,
    check_no_disable_torque,
)
from backend.reaction_bench.reverify import (
    fixture_dir_from_env,
    parse_capture,
    reverify_from_fixture,
)

__all__ = [
    "DEFAULT_REACTION_PATH_ROOT",
    "FIXTURE_ENV_VAR",
    "GATE",
    "REAL_CAPTURE_BASIS",
    "REFERENCE_NOTE",
    "REFERENCE_TARGETS_DECISION_NEEDED",
    "SEGMENT_ORDER",
    "SYNTHETIC_BASIS",
    "WP_ID",
    "DisableTorqueOnReactionPathError",
    "NoDisableTorqueCheck",
    "NonMonotonicSampleError",
    "ReactionLatencyRefusedError",
    "ReactionSample",
    "ReactionSegment",
    "ReactionTimeDecomposition",
    "assert_no_disable_torque",
    "assert_trusted_clock",
    "build_reaction_time_regression_artifact",
    "check_no_disable_torque",
    "fixture_dir_from_env",
    "parse_capture",
    "reverify_from_fixture",
]
