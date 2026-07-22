"""Assemble the WP-2A-06 stop-path regression evidence, refusing every un-trustworthy input.

WP-2A-06 re-measures PG-STOP-001 under the Wave 2A configuration and decomposes it. This
is where its three acceptance items come together, and each reuses a single-source rule
rather than restating it:

  * ③ The stop path must hold no `disable_torque` — run before anything else, delegated to
    the reused `backend.actuation` scan (`backend.stopbench.precondition`).
  * ② The total release-to-CAN P99 is published only with a trustworthy clock — delegated
    to WP-1-05's `build_stop_latency_artifact`, which owns the `clockProvenance` refusal
    (`03` §5.7.0). This bench never re-checks the clock; that rule has one home.
  * ① The four-stage path decomposition is recorded (`backend.stopbench.decompose`).

`THE ONE RULE` is that a run never fakes a green. The real on-rig latency needs torque-ON
and the kernel-clock instrumentation `03` §5.7.0 demands, neither of which exists on this
host, so an offline run is tagged `basis="synthetic-timestamps"`: its decomposition
machinery and refusals are real and run here, but its numbers are not a rig verdict. The
real numbers arrive only through the deferred re-verification hook, tagged
`basis="real-capture"`, and are judged by the identical refusals.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.rtbench.constants import REQUIRED_STALE_TRIGGER
from backend.stopbench.constants import (
    GATE,
    REFERENCE_TARGET_MS_UNCONFIRMED,
    WP_ID,
)
from backend.stopbench.decompose import StopPathDecomposition, StopPathSample
from backend.stopbench.precondition import (
    DEFAULT_STOP_PATH_ROOT,
    assert_no_disable_torque,
)
from backend.torque_bringup import ClockProvenance, build_stop_latency_artifact

# The offline basis: synthetic boundary timestamps, exercising the machinery on this host.
# Its numbers are not a rig measurement — the honest label that keeps an offline run from
# reading as a stop-latency verdict.
SYNTHETIC_BASIS = "synthetic-timestamps"
# The on-rig basis: real captured boundary timestamps supplied through the fixture hook.
REAL_CAPTURE_BASIS = "real-capture"


def build_stop_path_regression_artifact(
    *,
    samples: Sequence[StopPathSample],
    clock_provenance: ClockProvenance | None,
    stop_path_root: Path = DEFAULT_STOP_PATH_ROOT,
    basis: str = SYNTHETIC_BASIS,
    exclude: Iterable[Path] = (),
) -> dict[str, Any]:
    """Assemble the WP-2A-06 evidence, refusing it when a precondition fails.

    Args:
        samples: The stop-path samples; each is five boundary timestamps on one clock
            domain. Empty when the real measurement is deferred — the distributions are
            then empty, never fabricated.
        clock_provenance: How the sample clock was correlated (`03` §5.7.0); mandatory,
            and forwarded to WP-1-05's builder, which refuses a missing or forged one.
        stop_path_root: The stop-path tree scanned for `disable_torque` (acceptance ③).
        basis: `synthetic-timestamps` for an offline machinery run, `real-capture` for a
            fixture re-verification; recorded so an offline run never reads as a verdict.
        exclude: Directories to skip in the `disable_torque` scan.

    Returns:
        (dict[str, Any]) The evidence: the acceptance-③ precondition result, the reused
        clock-gated total-latency artifact (with its P99), the four-stage path
        decomposition, and the deferred-input manifest.

    Raises:
        DisableTorqueOnStopPathError: If the stop path holds `disable_torque` (③).
        StopLatencyArtifactRefusedError: If `clockProvenance` is absent or names the
            candump forge (②, raised by the reused WP-1-05 builder).
    """
    precondition = assert_no_disable_torque(stop_path_root, exclude=exclude)

    totals_sec = tuple(sample.total() for sample in samples)
    total_latency = build_stop_latency_artifact(
        samples_sec=totals_sec, clock_provenance=clock_provenance
    )

    decomposition = StopPathDecomposition(samples)

    return {
        "wp_id": WP_ID,
        "gate": GATE,
        "basis": basis,
        "generated_at": datetime.now(UTC).isoformat(),
        "stale_on": [REQUIRED_STALE_TRIGGER],
        "no_disable_torque_precondition": precondition.as_record(),
        "total_latency": total_latency,
        "path_decomposition": decomposition.as_record(),
        # Recorded as a reference, never a gate: 20 ms is `[unconfirmed]` and the measured
        # P99 is canon (`04` NFR-MAN-002, acceptance ②). No comparison is made here.
        "reference_target_ms_unconfirmed": REFERENCE_TARGET_MS_UNCONFIRMED,
        "reference_note": (
            "04 NFR-MAN-002's 20 ms is an [unconfirmed] target recorded for reference only; "
            "this bench renders no pass/fail on the latency (WP-2A-06 acceptance ②)"
        ),
        "deferred": _deferred_manifest(basis),
    }


def _deferred_manifest(basis: str) -> dict[str, Any]:
    """Record what the real measurement still needs and how to supply it.

    Args:
        basis: The basis of the artifact being assembled.

    Returns:
        (dict[str, Any]) The awaited inputs and the re-verification hook that consumes
        them, so the deferral is visible in the artifact rather than silent.
    """
    awaited = (
        []
        if basis == REAL_CAPTURE_BASIS
        else [
            "real deadman-release-to-CAN stop-path capture on a torque-ON rig",
            "kernel-clock instrumentation (03 §5.7.0: evdev kernel ts x SO_TIMESTAMPING, "
            "or an independent GPIO marker)",
        ]
    )
    return {
        "awaited_inputs": awaited,
        "reverification_hook": "backend.stopbench.reverify.reverify_from_fixture",
        "fixture_env_var": "OPENARM_STOPBENCH_REAL_FIXTURE",
        "note": (
            "the real stop-latency number needs rig torque-ON plus kernel-clock "
            "instrumentation; it is never asserted green offline (THE ONE RULE)"
        ),
    }
