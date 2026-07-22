"""Per-target preflight-latency bench (`03` §5.11), with the target numbers deferred.

The preflight's cost is the density-driven `mj_forward` walk (`02b` §3.3: denser sampling,
proportionally longer checks), and `03` §5.11 folds that latency into `PG-IK-001`, which is
judged PER TARGET across the four fleet computes. This bench runs the real walk on THIS host
and reports genuine percentiles — but `NFR-TEL-004` forbids using an x86 desktop figure as a
target verdict, so the host number is recorded reference-only and every target's slot stays
`DEFERRED` until a real on-target capture arrives through the re-verification hook.

`THE ONE RULE`: the machinery (the walk, the percentile math, the deferral manifest) is real
and runs here; the four target verdicts are never asserted green offline. The hook re-runs
the identical percentile math over on-target captures, so the deferred number cannot be
faked into existence — it is measured on the target or it does not exist.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from backend.collision_preflight.constants import (
    BENCH_TARGETS,
    FIXTURE_ENV_VAR,
    HOST_REFERENCE_BASIS,
    LATENCY_PERCENTILES,
    ON_TARGET_BASIS,
    TARGET_STATUS_DEFERRED,
    WP_ID,
)
from backend.collision_preflight.model import PreflightModel


def nearest_rank_percentile(samples_ms: tuple[float, ...], percentile: float) -> float:
    """Return a percentile of a sample set by nearest-rank.

    Args:
        samples_ms: The latency samples, milliseconds.
        percentile: The percentile to take, 0-100.

    Returns:
        (float) The nearest-rank percentile; 0.0 for an empty set.
    """
    if not samples_ms:
        return 0.0
    ordered = sorted(samples_ms)
    rank = max(1, min(len(ordered), round(percentile / 100.0 * len(ordered))))
    return ordered[rank - 1]


@dataclass(frozen=True)
class LatencySummary:
    """A latency distribution over per-waypoint `mj_forward` timings.

    Attributes:
        sample_count: How many waypoint timings were taken.
        percentiles_ms: Percentile-to-milliseconds, for `LATENCY_PERCENTILES`.
        mean_ms: The arithmetic mean, milliseconds.
    """

    sample_count: int
    percentiles_ms: dict[float, float]
    mean_ms: float

    def as_record(self) -> dict[str, Any]:
        """Render the summary for an artifact.

        Returns:
            (dict[str, Any]) The count, percentiles keyed by string, and mean.
        """
        return {
            "sample_count": self.sample_count,
            "percentiles_ms": {
                f"p{percentile:g}": value for percentile, value in self.percentiles_ms.items()
            },
            "mean_ms": self.mean_ms,
        }


def summarize_latencies(samples_ms: tuple[float, ...]) -> LatencySummary:
    """Summarize per-waypoint latencies into the reported percentiles and mean.

    Args:
        samples_ms: The per-waypoint latencies, milliseconds.

    Returns:
        (LatencySummary) The distribution summary.
    """
    percentiles = {
        percentile: nearest_rank_percentile(samples_ms, percentile)
        for percentile in LATENCY_PERCENTILES
    }
    mean = sum(samples_ms) / len(samples_ms) if samples_ms else 0.0
    return LatencySummary(sample_count=len(samples_ms), percentiles_ms=percentiles, mean_ms=mean)


def measure_host_latency(
    model: PreflightModel, trajectory: tuple[tuple[float, ...], ...], repeats: int
) -> LatencySummary:
    """Time the per-waypoint `mj_forward` walk on this host.

    Args:
        model: The loaded preflight model.
        trajectory: Waypoints, each a full-model configuration.
        repeats: How many passes over the trajectory to time; more passes, more samples.

    Returns:
        (LatencySummary) The per-waypoint latency distribution.
    """
    samples: list[float] = []
    for _ in range(repeats):
        for waypoint in trajectory:
            start = time.perf_counter()
            model.forward(waypoint)
            samples.append((time.perf_counter() - start) * 1000.0)
    return summarize_latencies(tuple(samples))


def build_preflight_bench_artifact(
    trajectory: tuple[tuple[float, ...], ...],
    *,
    margin_m: float,
    repeats: int = 3,
) -> dict[str, Any]:
    """Assemble the per-target latency bench, host-measured and target-deferred (`03` §5.11).

    Args:
        trajectory: Waypoints, each a full-model configuration of length `nq`.
        margin_m: The honoured collision margin to load the model with.
        repeats: Timing passes over the trajectory.

    Returns:
        (dict[str, Any]) The bench evidence: the real host-reference latency, a `DEFERRED`
        slot per fleet target, and the re-verification manifest.
    """
    model = PreflightModel(margin_m)
    host = measure_host_latency(model, trajectory, repeats)
    return {
        "wp_id": WP_ID,
        "gate": "PG-IK-001",
        "generated_at": datetime.now(UTC).isoformat(),
        "host_reference": {
            "basis": HOST_REFERENCE_BASIS,
            "latency": host.as_record(),
            "note": (
                "measured on an x86 host; NFR-TEL-004 forbids using it as a target verdict, "
                "so it is reference-only and renders no per-target PASS"
            ),
        },
        "targets": [
            {
                "target": target,
                "status": TARGET_STATUS_DEFERRED,
                "basis": ON_TARGET_BASIS,
                "latency": None,
            }
            for target in BENCH_TARGETS
        ],
        "deferred": {
            "awaited_inputs": [
                f"on-target preflight-latency capture on {', '.join(BENCH_TARGETS)}"
            ],
            "reverification_hook": "backend.collision_preflight.reverify.reverify_from_fixture",
            "fixture_env_var": FIXTURE_ENV_VAR,
            "note": (
                "each target's latency is measured on that target or it does not exist; it "
                "is never asserted green from an x86 figure (THE ONE RULE)"
            ),
        },
    }
