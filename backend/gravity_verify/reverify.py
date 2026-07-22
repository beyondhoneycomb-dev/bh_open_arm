"""Real-fixture re-verification hook for the deferred torque-ON pose-grid measurement.

Most of WP-2B-03 runs on this host: the residual table, the joint-2 anomaly check, the
link7->EE quantifier, and the FR-SAF-072 refusal all execute against synthetic measurements or
the committed v2 model. What cannot run here is the measurement itself — a real per-joint
`tau_meas` grid needs a torque-ON 40 Nm brakeless arm and an operator to align and hold each
pose (`SHAPE-HG`). That is deferred, not asserted green and not dropped.

This is the hook the deferral ships. When a directory of real captures is supplied through
`OPENARM_GRAVITY_VERIFY_REAL_FIXTURE`, `reverify_from_fixture` builds a REAL-basis grid from the
captured torques and runs the *identical* verification. The measured torque comes only from the
capture file — the hook never reads it from the model it is validating — so it cannot
manufacture a green (self-approval is structurally impossible here, and a real run is the only
one whose report is not provisional).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from backend.gravity.backend import Arm
from backend.gravity_verify.config import VerificationConfig
from backend.gravity_verify.errors import GravityVerifyError
from backend.gravity_verify.harness import VerificationReport, run_verification
from backend.gravity_verify.measurement import MeasurementBasis, PoseMeasurement

# Environment variable a caller sets to point the hook at a real capture directory.
FIXTURE_ENV_VAR = "OPENARM_GRAVITY_VERIFY_REAL_FIXTURE"


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


def _measurements_from_capture(capture: dict[str, Any]) -> tuple[PoseMeasurement, ...]:
    """Build a REAL-basis measurement grid from a capture's `samples` list.

    Each sample carries the held pose `q` and the measured joint torque `tau_meas`; the basis is
    fixed to REAL here, never read from the file, so a capture cannot claim to be synthetic-or-
    real at its own discretion.

    Args:
        capture: One parsed capture record with a `samples` list.

    Returns:
        (tuple[PoseMeasurement, ...]) The captured pose measurements, REAL basis.

    Raises:
        GravityVerifyError: On a capture with no samples.
    """
    samples = capture.get("samples", [])
    if not samples:
        raise GravityVerifyError("real capture holds no samples")
    return tuple(
        PoseMeasurement(
            q=tuple(float(angle) for angle in point["q"]),
            tau_meas=tuple(float(torque) for torque in point["tau_meas"]),
            basis=MeasurementBasis.REAL,
        )
        for point in samples
    )


def reverify_from_fixture(fixture_dir: Path, arm: Arm = Arm.RIGHT) -> list[VerificationReport]:
    """Re-run the WP-2B-03 verification against real captured torque grids.

    Loads every `*.json` capture in the directory and runs the identical residual/anomaly/
    link7 verification, now pointed at real measured torques with `use_velocity_and_torque=true`
    (a real torque grid could not exist without it). This is the re-verification the deferred
    on-rig acceptance requires; each report is on the REAL basis and is not provisional.

    Args:
        fixture_dir: Directory of captured measurement JSON files, one per session.
        arm: Which follower arm the captures are for.

    Returns:
        (list[VerificationReport]) One report per capture file, ordered by filename.

    Raises:
        FileNotFoundError: If the directory holds no `*.json` capture.
        GravityVerifyError: If a capture is empty or malformed.
    """
    capture_files = sorted(fixture_dir.glob("*.json"))
    if not capture_files:
        raise FileNotFoundError(f"no *.json gravity-verify capture in {fixture_dir}")
    reports: list[VerificationReport] = []
    for path in capture_files:
        capture = json.loads(path.read_text(encoding="utf-8"))
        grid = _measurements_from_capture(capture)
        config = VerificationConfig(use_velocity_and_torque=True, arm=arm)
        reports.append(run_verification(grid, config))
    return reports
