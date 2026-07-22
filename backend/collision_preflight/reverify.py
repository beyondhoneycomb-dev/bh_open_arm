"""Real on-target re-verification for the deferred per-target preflight latency (`03` §5.11).

The bench (`backend.collision_preflight.bench`) runs the real `mj_forward` walk on this host
but leaves every fleet target `DEFERRED`, because `NFR-TEL-004` bars an x86 figure from being
a target verdict. This is the hook that deferral ships: when a directory of real on-target
latency captures is supplied via `OPENARM_COLLISION_PREFLIGHT_REAL_FIXTURE`, it re-runs the
IDENTICAL percentile math over the on-target samples and produces one summary per target.

It renders percentiles, never a pass line: the `PG-IK-001` collision-latency budget is still
`[unmeasured]` (`03` §5.11), so a green here would be invented. The hook reports what the
target measured; a capture with an unknown target or no samples is refused exactly as it
would be, so the deferred number can only ever come from a real on-target measurement.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.collision_preflight.bench import LatencySummary, summarize_latencies
from backend.collision_preflight.constants import (
    BENCH_TARGETS,
    FIXTURE_ENV_VAR,
    ON_TARGET_BASIS,
)


@dataclass(frozen=True)
class TargetLatencyVerification:
    """The latency verdict one on-target capture produced.

    Attributes:
        target: The fleet target the capture came from.
        summary: The re-computed latency distribution, or None when refused.
        refusal: Why the capture was refused, empty when it verified.
    """

    target: str
    summary: LatencySummary | None
    refusal: str

    def as_record(self) -> dict[str, Any]:
        """Render the verification for an artifact.

        Returns:
            (dict[str, Any]) The target, basis, summary (or null), and refusal.
        """
        return {
            "target": self.target,
            "basis": ON_TARGET_BASIS,
            "latency": None if self.summary is None else self.summary.as_record(),
            "refusal": self.refusal,
        }


def fixture_dir_from_env() -> Path | None:
    """Return the real-fixture directory named by the environment, if set and present.

    Returns:
        (Path | None) The directory, or None when unset or absent.
    """
    raw = os.environ.get(FIXTURE_ENV_VAR)
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_dir() else None


def _verify_one(capture: dict[str, Any]) -> TargetLatencyVerification:
    """Re-run the percentile math over one on-target latency capture.

    Args:
        capture: One parsed capture: `{target, samples_ms: [...]}`.

    Returns:
        (TargetLatencyVerification) The verdict; summary set only for a trustworthy capture.
    """
    target = str(capture.get("target", ""))
    if target not in BENCH_TARGETS:
        return TargetLatencyVerification(
            target=target,
            summary=None,
            refusal=f"target {target!r} is not one of the fleet targets {BENCH_TARGETS}",
        )
    raw_samples = capture.get("samples_ms", [])
    if not raw_samples:
        return TargetLatencyVerification(
            target=target, summary=None, refusal="capture holds no samples_ms"
        )
    samples = tuple(float(value) for value in raw_samples)
    return summarize_target(target, samples)


def summarize_target(target: str, samples_ms: tuple[float, ...]) -> TargetLatencyVerification:
    """Summarize one target's on-target latency samples through the shared math.

    Args:
        target: The fleet target.
        samples_ms: The on-target per-waypoint latencies, milliseconds.

    Returns:
        (TargetLatencyVerification) The verified summary.
    """
    return TargetLatencyVerification(
        target=target, summary=summarize_latencies(samples_ms), refusal=""
    )


def reverify_from_fixture(fixture_dir: Path) -> list[TargetLatencyVerification]:
    """Re-run the latency math against real on-target captures.

    Loads every `*.json` capture in the directory and re-applies the same percentile math
    the bench uses, now over on-target samples. This is the re-verification the deferred
    per-target latency requires; it renders no pass line (the budget is unmeasured).

    Args:
        fixture_dir: Directory of on-target latency JSON captures, one per target.

    Returns:
        (list[TargetLatencyVerification]) One verification per capture, ordered by filename.

    Raises:
        FileNotFoundError: If the directory holds no `*.json` capture.
    """
    capture_files = sorted(fixture_dir.glob("*.json"))
    if not capture_files:
        raise FileNotFoundError(f"no *.json latency capture in {fixture_dir}")
    return [_verify_one(json.loads(path.read_text(encoding="utf-8"))) for path in capture_files]
