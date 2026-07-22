"""Real-fixture re-verification hook for the deferred on-rig stop-latency measurement.

Most of WP-2A-06 runs on this host: the `disable_torque` precondition, the four-stage
decomposition machinery, and the `clockProvenance` refusal all execute against synthetic
boundary timestamps. What cannot run here is the measurement itself — a real
deadman-release-to-CAN-stop capture needs a torque-ON rig and the kernel-clock
instrumentation `03` §5.7.0 requires (evdev kernel timestamp crossed with SO_TIMESTAMPING,
or an independent GPIO marker). That is deferred, not asserted green and not dropped.

This is the hook the deferral is required to ship (`02a` §4.1). The moment a directory of
real captures is supplied via `OPENARM_STOPBENCH_REAL_FIXTURE`, `reverify_from_fixture`
re-runs the *identical* bench — the same precondition, the same decomposition, and the same
reused WP-1-05 `clockProvenance` refusal — against the real timestamps. A capture that
names the candump forge as its clock method is refused exactly as a synthetic one would be,
so the hook can never manufacture the bus number `THE ONE RULE` forbids.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from backend.stopbench.bench import REAL_CAPTURE_BASIS, build_stop_path_regression_artifact
from backend.stopbench.decompose import StopPathSample
from backend.torque_bringup import ClockProvenance

# Environment variable a caller sets to point the hook at a real capture directory.
FIXTURE_ENV_VAR = "OPENARM_STOPBENCH_REAL_FIXTURE"


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


def _samples_from_capture(capture: dict[str, Any]) -> tuple[StopPathSample, ...]:
    """Build stop-path samples from a real capture's `samples` list.

    Args:
        capture: One parsed capture record.

    Returns:
        (tuple[StopPathSample, ...]) The captured five-boundary samples.
    """
    return tuple(
        StopPathSample(
            lease_expiry_at=float(point["lease_expiry_at"]),
            transmit_at=float(point["transmit_at"]),
            scheduler_at=float(point["scheduler_at"]),
            can_write_at=float(point["can_write_at"]),
            can_first_byte_at=float(point["can_first_byte_at"]),
        )
        for point in capture.get("samples", [])
    )


def _clock_provenance_from_capture(capture: dict[str, Any]) -> ClockProvenance:
    """Build the clock provenance from a real capture.

    A missing provenance is left to the reused WP-1-05 builder to refuse, rather than
    defaulted here — defaulting it would be the forgery the gate exists to prevent.

    Args:
        capture: One parsed capture record.

    Returns:
        (ClockProvenance) The provenance as captured; may name a method the builder
        refuses.
    """
    provenance = capture["clock_provenance"]
    return ClockProvenance(
        method=str(provenance["method"]),
        offset_sec=float(provenance["offset_sec"]),
        uncertainty_sec=float(provenance["uncertainty_sec"]),
    )


def parse_capture(capture: dict[str, Any]) -> tuple[tuple[StopPathSample, ...], ClockProvenance]:
    """Parse a capture record into the bench's two inputs.

    Shared by the fixture hook and the CLI so both read a capture the same way.

    Args:
        capture: One parsed capture record: `samples` and `clock_provenance`.

    Returns:
        (tuple) The five-boundary samples and the captured clock provenance.
    """
    return _samples_from_capture(capture), _clock_provenance_from_capture(capture)


def reverify_from_fixture(fixture_dir: Path) -> list[dict[str, Any]]:
    """Re-run the WP-2A-06 bench against real captured stop-path measurements.

    Loads every `*.json` capture in the directory and runs the identical
    precondition/decomposition/clock-refusal bench, now pointed at real boundary
    timestamps and a real `clockProvenance`. This is the re-verification the deferred
    on-rig acceptance requires.

    Args:
        fixture_dir: Directory of captured measurement JSON files, one per host.

    Returns:
        (list[dict[str, Any]]) One evidence artifact per capture file, ordered by
        filename, each tagged `basis="real-capture"`.

    Raises:
        FileNotFoundError: If the directory holds no `*.json` capture.
        DisableTorqueOnStopPathError: If the stop path holds `disable_torque`.
        StopLatencyArtifactRefusedError: If a capture's clock cannot be trusted.
    """
    capture_files = sorted(fixture_dir.glob("*.json"))
    if not capture_files:
        raise FileNotFoundError(f"no *.json stopbench capture in {fixture_dir}")
    artifacts: list[dict[str, Any]] = []
    for path in capture_files:
        capture = json.loads(path.read_text(encoding="utf-8"))
        samples, clock_provenance = parse_capture(capture)
        artifacts.append(
            build_stop_path_regression_artifact(
                samples=samples,
                clock_provenance=clock_provenance,
                basis=REAL_CAPTURE_BASIS,
            )
        )
    return artifacts
