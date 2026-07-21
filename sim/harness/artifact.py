"""Artifact assembly and its refusal guards — where the acceptance clauses bite.

The artifact is the harness's published output. Two acceptance clauses are enforced
here, as hard refusals rather than warnings, because `THE ONE RULE` is that a run
must never fake an acceptance:

  * ② The four load parameters must be recorded. A run whose profile is not fully
    recorded is refused publication — an artifact that cannot be compared against the
    real measurement (`b`, 03 §5.1a) has no value, so it is not written at all.
  * ⑥ Every timing condition must carry its full distribution — raw samples and a
    complete binned histogram. A summary-only artifact (p50/p95/p99 with the
    distribution thrown away) is refused.

The manifest carries the `env_hash` and `normalization_hash` (`06` §2.2), stamped
from the values `WP-ENV-04` and `WP-N1-04` currently publish, exactly as the Wave 0-C
dataset provenance does. The launch barriers, not this module, decide whether those
hashes clear; the manifest's job is only to declare them honestly.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from registry.env.env_hash import read_issued as read_env_hash
from registry.normalization.content_hash import ISSUED_PATH as NORMALIZATION_ISSUED_PATH
from registry.normalization.content_hash import read_issued as read_normalization_hash
from sim.harness.conditions import ConditionResult
from sim.harness.harness import HarnessResult
from sim.harness.load_profile import profile_is_fully_recorded

WP_ID = "WP-0C-06"


class ArtifactRefusedError(Exception):
    """The artifact violated an acceptance clause and was refused publication.

    Raised instead of writing a defective artifact, so a run that did not record its
    load parameters (②) or that would publish summary statistics without the full
    distribution (⑥) fails loudly rather than emitting a green-looking result.
    """


def build_manifest() -> dict[str, Any]:
    """Build the env/normalization manifest for a harness artifact.

    Returns:
        (dict[str, Any]) `wp_id` plus the two currently-issued hashes. When a hash is
        not yet published the slot is None, which the barrier reads as "declares no
        hash" and refuses start — never a fabricated value.
    """
    return {
        "wp_id": WP_ID,
        "env_hash": read_env_hash(),
        "normalization_hash": read_normalization_hash(NORMALIZATION_ISSUED_PATH),
    }


def _condition_record(result: ConditionResult, overrun_tolerance: float) -> dict[str, Any]:
    """Serialize one condition result, embedding its full distribution when timing.

    Args:
        result: The condition result.
        overrun_tolerance: The fractional slack above the period for the overrun rate.

    Returns:
        (dict[str, Any]) The condition's record. Timing conditions carry the full
        `distribution` (raw samples + histogram) and the overrun rate; the frame-count
        condition carries only its modelled fields.
    """
    record: dict[str, Any] = {
        "number": result.number,
        "key": result.key,
        "title": result.title,
        "is_timing": result.is_timing,
        "extra": result.extra,
    }
    if result.is_timing and result.histogram is not None and result.period_sec is not None:
        record["period_sec"] = result.period_sec
        record["overrun_tolerance"] = overrun_tolerance
        record["overrun_rate"] = result.histogram.overrun_rate(result.period_sec, overrun_tolerance)
        record["distribution"] = result.histogram.as_record()
    return record


def _assert_profile_recorded(profile_record: dict[str, Any] | None) -> None:
    """Refuse the artifact unless all four load parameters are recorded (②).

    Args:
        profile_record: The load-profile record to check.

    Raises:
        ArtifactRefusedError: If any of the four canonical parameters is absent.
    """
    if not profile_is_fully_recorded(profile_record):
        raise ArtifactRefusedError(
            "load profile is not fully recorded; the four parameters "
            "{stream_count, resolution, png_write_bytes_per_frame, serialize_bytes_per_tick} "
            "must all be present (acceptance ②)"
        )


def _assert_full_histograms(condition_records: list[dict[str, Any]]) -> None:
    """Refuse the artifact unless every timing condition carries its full distribution (⑥).

    Args:
        condition_records: The serialized condition records.

    Raises:
        ArtifactRefusedError: If a timing condition is missing raw samples or histogram bins.
    """
    for record in condition_records:
        if not record.get("is_timing"):
            continue
        distribution = record.get("distribution")
        if not distribution:
            raise ArtifactRefusedError(
                f"condition {record.get('key')} is a timing condition but carries no "
                "distribution; full histograms are required (acceptance ⑥)"
            )
        if not distribution.get("raw_samples") or not distribution.get("histogram", {}).get(
            "counts"
        ):
            raise ArtifactRefusedError(
                f"condition {record.get('key')} would publish summary statistics without "
                "the full distribution; raw samples and histogram bins are required "
                "(acceptance ⑥)"
            )


def _acceptance_map() -> dict[str, str]:
    """Map each acceptance clause to where its evidence lives in the artifact.

    Returns:
        (dict[str, str]) Clause id to a human pointer, so a reviewer can check each
        clause against the artifact without reading the harness source.
    """
    return {
        "1_conditions_auto_runnable": "conditions[] — all seven produced with no manual step",
        "2_load_profile_recorded": "load_profile — four params; unrecorded run is refused",
        "3_load_bites": "load_distinguishability — condition 4 vs condition 1 rank test",
        "4_gil_contribution": "gil_contribution — condition 4 median minus condition 5 median",
        "5_rt_before_after": "conditions[5].extra.rt_promotion + median_gain_sec (no-gain valid)",
        "6_full_histograms": "conditions[].distribution — raw samples + histogram, not a summary",
        "7_self_overhead": "self_overhead — instrument per-sample cost, measured separately",
        "8_no_numeric_target": "fmax_python_provisional — provisional:true, is_verdict:false",
    }


def build_artifact(result: HarnessResult) -> dict[str, Any]:
    """Assemble the publishable artifact, refusing it if an acceptance clause is violated.

    Args:
        result: A completed harness run.

    Returns:
        (dict[str, Any]) The full artifact: manifest, load profile, every condition's
        full distribution, the derived basis metrics, and the acceptance map.

    Raises:
        ArtifactRefusedError: If the load profile is not fully recorded (②) or any timing
            condition would be published without its full distribution (⑥).
    """
    profile_record = result.profile.as_record()
    _assert_profile_recorded(profile_record)

    tolerance = result.config.overrun_tolerance
    condition_records = [_condition_record(condition, tolerance) for condition in result.conditions]
    _assert_full_histograms(condition_records)

    return {
        "wp_id": WP_ID,
        "gate": "PG-RT-001a",
        "gate_status": "provisional",
        "generated_at": datetime.now(UTC).isoformat(),
        "manifest": build_manifest(),
        "load_profile": profile_record,
        "measurement_config": {
            "target_hz": result.config.target_hz,
            "tick_count": result.config.tick_count,
            "warmup": result.config.warmup,
            "sweep_frequencies_hz": list(result.config.sweep_frequencies_hz),
            "sweep_tick_count": result.config.sweep_tick_count,
            "overrun_tolerance": result.config.overrun_tolerance,
        },
        "self_overhead": result.self_overhead,
        "conditions": condition_records,
        "load_distinguishability": result.load_distinguishability.as_record(),
        "gil_contribution": result.gil_contribution,
        "fmax_sweep": result.fmax_sweep,
        "fmax_python_provisional": result.fmax_python_provisional,
        "connect_call_count": result.connect_call_count,
        "acceptance_map": _acceptance_map(),
    }


def write_artifact(result: HarnessResult, path: Path) -> dict[str, Any]:
    """Build the artifact and write it to disk as JSON.

    Args:
        result: A completed harness run.
        path: Where to write the artifact JSON.

    Returns:
        (dict[str, Any]) The artifact that was written.

    Raises:
        ArtifactRefusedError: If assembly refuses the artifact (②, ⑥).
    """
    artifact = build_artifact(result)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    return artifact
