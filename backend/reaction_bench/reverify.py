"""Real-fixture re-verification hook for the deferred on-rig reaction-time measurement.

Most of WP-2C-06 runs on this host: the `disable_torque` precondition, the three-stage
decomposition machinery, and the trusted-clock refusal all execute against synthetic
boundary timestamps. What cannot run here is the measurement itself — a real
detection-confirm-to-CAN reaction-frame capture needs a torque-ON rig and the kernel-clock
instrumentation `03` §5.7.0 requires (an evdev kernel timestamp crossed with SO_TIMESTAMPING,
or an independent GPIO marker). That is deferred, not asserted green and not dropped.

This is the hook the deferral is required to ship (`02a` §4.1). The moment a directory of
real captures is supplied via `OPENARM_REACTION_BENCH_REAL_FIXTURE`, `reverify_from_fixture`
re-runs the *identical* bench — the same precondition, the same decomposition, and the same
trusted-clock refusal — against the real timestamps. A capture that names the candump forge
as its clock is refused exactly as a synthetic one would be, so the hook can never
manufacture the reaction-time number `THE ONE RULE` forbids.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from backend.reaction_bench.bench import REAL_CAPTURE_BASIS, build_reaction_time_regression_artifact
from backend.reaction_bench.constants import FIXTURE_ENV_VAR
from backend.reaction_bench.latency import ReactionSample
from backend.torque_bringup import ClockProvenance


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


def _samples_from_capture(capture: dict[str, Any]) -> tuple[ReactionSample, ...]:
    """Build reaction samples from a real capture's `samples` list.

    Args:
        capture: One parsed capture record.

    Returns:
        (tuple[ReactionSample, ...]) The captured four-boundary samples.
    """
    return tuple(
        ReactionSample(
            detection_confirm_at=float(point["detection_confirm_at"]),
            reaction_select_at=float(point["reaction_select_at"]),
            scheduler_write_at=float(point["scheduler_write_at"]),
            can_first_byte_at=float(point["can_first_byte_at"]),
        )
        for point in capture.get("samples", [])
    )


def _clock_provenance_from_capture(capture: dict[str, Any]) -> ClockProvenance:
    """Build the clock provenance from a real capture.

    A missing provenance is left to `assert_trusted_clock` to refuse, rather than defaulted
    here — defaulting it would be the forgery the refusal exists to prevent.

    Args:
        capture: One parsed capture record.

    Returns:
        (ClockProvenance) The provenance as captured; may name a method the bench refuses.
    """
    provenance = capture["clock_provenance"]
    return ClockProvenance(
        method=str(provenance["method"]),
        offset_sec=float(provenance["offset_sec"]),
        uncertainty_sec=float(provenance["uncertainty_sec"]),
    )


def parse_capture(capture: dict[str, Any]) -> tuple[tuple[ReactionSample, ...], ClockProvenance]:
    """Parse a capture record into the bench's two inputs.

    Shared by the fixture hook and the CLI so both read a capture the same way.

    Args:
        capture: One parsed capture record: `samples` and `clock_provenance`.

    Returns:
        (tuple) The four-boundary samples and the captured clock provenance.
    """
    return _samples_from_capture(capture), _clock_provenance_from_capture(capture)


def reverify_from_fixture(fixture_dir: Path) -> list[dict[str, Any]]:
    """Re-run the WP-2C-06 bench against real captured reaction-time measurements.

    Loads every `*.json` capture in the directory and runs the identical
    precondition/decomposition/clock-refusal bench, now pointed at real boundary timestamps
    and a real `clockProvenance`. This is the re-verification the deferred on-rig acceptance
    requires.

    Args:
        fixture_dir: Directory of captured measurement JSON files, one per host.

    Returns:
        (list[dict[str, Any]]) One evidence artifact per capture file, ordered by filename,
        each tagged `basis="real-capture"`.

    Raises:
        FileNotFoundError: If the directory holds no `*.json` capture.
        DisableTorqueOnReactionPathError: If the reaction path holds `disable_torque`.
        ReactionLatencyRefusedError: If a capture's clock cannot be trusted.
    """
    capture_files = sorted(fixture_dir.glob("*.json"))
    if not capture_files:
        raise FileNotFoundError(f"no *.json reaction_bench capture in {fixture_dir}")
    artifacts: list[dict[str, Any]] = []
    for path in capture_files:
        capture = json.loads(path.read_text(encoding="utf-8"))
        samples, clock_provenance = parse_capture(capture)
        artifacts.append(
            build_reaction_time_regression_artifact(
                samples=samples,
                clock_provenance=clock_provenance,
                basis=REAL_CAPTURE_BASIS,
            )
        )
    return artifacts
