"""Assemble the WP-2C-06 reaction-time evidence, refusing every un-trustworthy input.

WP-2C-06 measures the detection-confirm -> first-reaction-MIT-frame latency and records its
histogram (`02b` WP-2C-06 acceptance 1). This is where its parts come together, each reusing
a single-source rule rather than restating it:

  * The reaction path must hold no `disable_torque` — run before anything else, delegated to
    the reused `backend.actuation` scan (`backend.reaction_bench.precondition`).
  * The confirm-to-CAN-first-byte interval is only trustworthy under a trusted clock —
    delegated to `backend.reaction_bench.clock`, which reuses WP-1-05's single-source
    `ALLOWED_CLOCK_METHODS` and refuses an absent or forged provenance.
  * The three-stage path decomposition and the full histograms are recorded
    (`backend.reaction_bench.latency`, reusing the WP-0C-06 histogram).

`THE ONE RULE` is that a run never fakes a green. The real on-rig reaction time needs
torque-ON and the kernel-clock instrumentation `03` §5.7.0 demands, neither of which exists
on this host, so an offline run is tagged `basis="synthetic-timestamps"`: its decomposition
machinery and refusals are real and run here, but its numbers are not a rig verdict. The
real numbers arrive only through the deferred re-verification hook, tagged
`basis="real-capture"`, and are judged by the identical refusals. No pass line is applied at
either basis — NFR-SAF-002/003/004 are all decision-needed and fixed after measurement by a
regression gate (`02b` WP-2C-06 acceptance 2).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.reaction_bench.clock import assert_trusted_clock
from backend.reaction_bench.constants import (
    GATE,
    REFERENCE_NOTE,
    REFERENCE_TARGETS_DECISION_NEEDED,
    WP_ID,
)
from backend.reaction_bench.latency import ReactionSample, ReactionTimeDecomposition
from backend.reaction_bench.precondition import (
    DEFAULT_REACTION_PATH_ROOT,
    assert_no_disable_torque,
)
from backend.torque_bringup import ClockProvenance

# The offline basis: synthetic boundary timestamps, exercising the machinery on this host.
# Its numbers are not a rig measurement — the honest label that keeps an offline run from
# reading as a reaction-time verdict.
SYNTHETIC_BASIS = "synthetic-timestamps"
# The on-rig basis: real captured boundary timestamps supplied through the fixture hook.
REAL_CAPTURE_BASIS = "real-capture"


def build_reaction_time_regression_artifact(
    *,
    samples: Sequence[ReactionSample],
    clock_provenance: ClockProvenance | None,
    reaction_path_root: Path = DEFAULT_REACTION_PATH_ROOT,
    basis: str = SYNTHETIC_BASIS,
    exclude: Iterable[Path] = (),
) -> dict[str, Any]:
    """Assemble the WP-2C-06 evidence, refusing it when a precondition fails.

    Args:
        samples: The reaction samples; each is four boundary timestamps on one clock domain.
            Empty when the real measurement is deferred — the distributions are then empty,
            never fabricated.
        clock_provenance: How the sample clock was correlated (`03` §5.7.0); mandatory, and
            refused when absent or a forge.
        reaction_path_root: The reaction-path tree scanned for `disable_torque`.
        basis: `synthetic-timestamps` for an offline machinery run, `real-capture` for a
            fixture re-verification; recorded so an offline run never reads as a verdict.
        exclude: Directories to skip in the `disable_torque` scan.

    Returns:
        (dict[str, Any]) The evidence: the `disable_torque` precondition result, the trusted
        clock provenance, the three-stage reaction-time decomposition with its full
        histograms, the decision-needed reference targets, and the deferred-input manifest.

    Raises:
        DisableTorqueOnReactionPathError: If the reaction path holds `disable_torque`.
        ReactionLatencyRefusedError: If `clockProvenance` is absent or names the candump forge.
    """
    precondition = assert_no_disable_torque(reaction_path_root, exclude=exclude)
    trusted_clock = assert_trusted_clock(clock_provenance)

    decomposition = ReactionTimeDecomposition(samples)

    return {
        "wp_id": WP_ID,
        "gate": GATE,
        "basis": basis,
        "generated_at": datetime.now(UTC).isoformat(),
        "no_disable_torque_precondition": precondition.as_record(),
        "clock_provenance": trusted_clock.as_record(),
        "reaction_time": decomposition.as_record(),
        # Recorded as references, never gates: NFR-SAF-002/003/004 are all decision-needed
        # and the measured distribution is canon (`02b` WP-2C-06 acceptance 2). No comparison
        # is made here.
        "reference_targets_decision_needed": list(REFERENCE_TARGETS_DECISION_NEEDED),
        "reference_note": REFERENCE_NOTE,
        "deferred": _deferred_manifest(basis),
    }


def _deferred_manifest(basis: str) -> dict[str, Any]:
    """Record what the real measurement still needs and how to supply it.

    Args:
        basis: The basis of the artifact being assembled.

    Returns:
        (dict[str, Any]) The awaited inputs and the re-verification hook that consumes them,
        so the deferral is visible in the artifact rather than silent.
    """
    awaited = (
        []
        if basis == REAL_CAPTURE_BASIS
        else [
            "real detection-confirm-to-CAN reaction-frame capture on a torque-ON rig",
            "kernel-clock instrumentation (03 §5.7.0: evdev kernel ts x SO_TIMESTAMPING, "
            "or an independent GPIO marker)",
        ]
    )
    return {
        "awaited_inputs": awaited,
        "reverification_hook": "backend.reaction_bench.reverify.reverify_from_fixture",
        "fixture_env_var": "OPENARM_REACTION_BENCH_REAL_FIXTURE",
        "note": (
            "the real reaction time needs rig torque-ON plus kernel-clock instrumentation; "
            "it is never asserted green offline (THE ONE RULE)"
        ),
    }
