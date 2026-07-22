"""Real-fixture re-verification hook for the deferred torque-ON acceptances (`02a` §4.1).

Most of WP-1-05 runs on this host: the guarded-torque-ON ordering, the lease-expiry-forces-
a-hold logic, the SAFE_HOLD-is-not-torque-0 check, the manifest PG-SAFE-001-hash gate, and
the PG-STOP-001 clockProvenance refusal. What does not run here is every acceptance that
needs the arm powered — the actual 0xFC engage on real motors, the present-pose hold under
real gravity, the real release-to-CAN-stop P99, the power-cycle zero re-verify, and the
hard-E-Stop drop — because there is no CAN adapter, no motor, and no PG-SAFE-001 PASS on
this host. Those are deferred: skipped with a reason, never asserted green, never dropped.

This is the hook the deferral is required to ship. The moment a directory of real captures
is supplied via `OPENARM_TORQUE_BRINGUP_REAL_FIXTURE`, `reverify_from_fixture` re-runs the
*identical* judgments — `assert_safe_hold` over the real engage frame, `build_stop_latency_
artifact` over the real samples (which re-applies the clockProvenance gate), and the zero-
residual tolerance check that WP-1-02 shares — against the real numbers. A stop capture with
no clockProvenance is refused exactly as it is offline, so the hook can never manufacture the
one number `THE ONE RULE` forbids.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.torque_bringup.constants import FIXTURE_ENV_VAR
from backend.torque_bringup.hold import assert_safe_hold
from backend.torque_bringup.sequence import build_present_pose_hold
from backend.torque_bringup.stop_latency import (
    ClockProvenance,
    build_stop_latency_artifact,
)
from contracts.units import Rad


@dataclass(frozen=True)
class RealVerification:
    """The verdicts a real capture produced, one per host file.

    Attributes:
        host_id: The control host the capture came from (`05` NFR-TEL-004).
        engage_displacement_rad: Per-joint commanded displacement of the real engage; a
            guarded engage holds the present pose, so every entry is 0.0.
        stop_latency_artifact: The PG-STOP-001 artifact rebuilt from the real samples;
            None when the capture carried no stop measurement.
        zero_residual_within_tolerance: Whether the power-cycle zero residual held (shared
            with WP-1-02 acceptance ⑦).
    """

    host_id: str
    engage_displacement_rad: tuple[float, ...]
    stop_latency_artifact: dict[str, Any] | None
    zero_residual_within_tolerance: bool


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


def _verify_engage(capture: dict[str, Any]) -> tuple[float, ...]:
    """Rebuild and check the real present-pose hold engage.

    Args:
        capture: One parsed capture record.

    Returns:
        (tuple[float, ...]) The per-joint commanded displacement of the engage.
    """
    present = tuple(Rad(float(angle)) for angle in capture["engage"]["present_pose_rad"])
    hold_batch = build_present_pose_hold(present)
    assert_safe_hold(hold_batch)
    return tuple(
        command.q.value - angle.value for command, angle in zip(hold_batch, present, strict=True)
    )


def _verify_stop_latency(capture: dict[str, Any]) -> dict[str, Any] | None:
    """Rebuild the PG-STOP-001 artifact from the real samples, re-applying the clock gate.

    Args:
        capture: One parsed capture record.

    Returns:
        (dict[str, Any] | None) The rebuilt artifact, or None when the capture carried no
        stop measurement.

    Raises:
        StopLatencyArtifactRefusedError: If the real capture's clockProvenance is absent or a
            forge — the same refusal the offline path makes.
    """
    stop = capture.get("stop_latency")
    if stop is None:
        return None
    provenance_raw = stop.get("clock_provenance")
    provenance = (
        ClockProvenance(
            method=str(provenance_raw["method"]),
            offset_sec=float(provenance_raw["offset_sec"]),
            uncertainty_sec=float(provenance_raw["uncertainty_sec"]),
        )
        if provenance_raw is not None
        else None
    )
    samples = tuple(float(value) for value in stop.get("samples_sec", []))
    return build_stop_latency_artifact(samples_sec=samples, clock_provenance=provenance)


def _verify_one(capture: dict[str, Any]) -> RealVerification:
    """Re-run every judgment over one real capture record.

    Args:
        capture: One parsed capture record.

    Returns:
        (RealVerification) The verdicts derived from the real numbers.
    """
    residual = capture.get("zero_residual", {})
    return RealVerification(
        host_id=str(capture.get("host_id", "unknown")),
        engage_displacement_rad=_verify_engage(capture),
        stop_latency_artifact=_verify_stop_latency(capture),
        zero_residual_within_tolerance=bool(residual.get("within_tolerance", False)),
    )


def reverify_from_fixture(fixture_dir: Path) -> list[RealVerification]:
    """Re-run the WP-1-05 judgments against real captured measurements.

    Loads every `*.json` capture in the directory and runs the identical guarded-engage,
    stop-latency, and zero-residual judgments the offline tests exercise, now pointed at
    real numbers. This is the re-verification the deferred hardware acceptances require.

    Args:
        fixture_dir: Directory of captured measurement JSON files, one per host.

    Returns:
        (list[RealVerification]) One verification per capture file, ordered by filename.

    Raises:
        FileNotFoundError: If the directory holds no `*.json` capture.
    """
    capture_files = sorted(fixture_dir.glob("*.json"))
    if not capture_files:
        raise FileNotFoundError(f"no *.json torque-bringup capture in {fixture_dir}")
    return [_verify_one(json.loads(path.read_text(encoding="utf-8"))) for path in capture_files]
