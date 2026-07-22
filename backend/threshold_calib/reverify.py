"""Real-fixture re-verification for the deferred calibration run (`02a` §4.1).

Everything the wizard needs runs on this host except the calibration run itself: the
collector, both proposal rules, the floor and effort bounds, the display and the canon
refusal are all exercised offline against a synthetic residual stream. What does not run
here is a real collision-free run — it needs a powered arm, WP-2C-01's live residual, and an
operator watching for contact, and there is no CAN, no motor and no operator on a desktop.
It is deferred: skipped with a reason, never asserted green.

This is the hook that deferral ships. Given a directory of real residual captures — each a
representative trajectory's runs plus the operator's no-collision judgment — the hook re-runs
the *identical* collector-proposer-bounds pipeline over the real samples. The floor and
effort cap come from physics (imported through the proposer), never from the capture, and the
canon verdict comes from the operator's attestation, never from the file asserting it: a
capture that did not attest no-collision yields a recorded but non-canonical calibration, so
the hook can never manufacture the measured-threshold pass THE ONE RULE forbids.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from backend.threshold_calib.collector import collector_for_arm
from backend.threshold_calib.constants import (
    FIXTURE_ENV_VAR,
    METHOD_MAX_PLUS_SIGMA,
    METHOD_NOMINAL_SCALED,
    NOMINAL_SCALE_DEFAULT,
)
from backend.threshold_calib.proposer import (
    ThresholdProposal,
    propose_max_plus_sigma,
    propose_nominal_scaled,
)
from backend.threshold_calib.wizard import (
    Calibration,
    NoCollisionJudgment,
    attested_calibration,
)


@dataclass(frozen=True)
class RealCalibrationVerification:
    """The verdict a real collision-free residual capture produced.

    Attributes:
        trajectory_id: The representative trajectory the capture swept.
        calibration: The calibration built from the real run, canonical only when the
            operator attested no collision; None when the capture was refused.
        refusal: The refusal reason when the capture failed validation, else empty.
    """

    trajectory_id: str
    calibration: Calibration | None
    refusal: str


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


def _proposal_for(method: str, stats: Any, nominal_scale: float) -> ThresholdProposal:
    """Run the requested proposal rule over collected statistics.

    Args:
        method: The proposal method identifier from the capture.
        stats: Per-joint residual statistics from the collector.
        nominal_scale: The margin for the nominal-scaled rule.

    Returns:
        (ThresholdProposal) The bounded proposal.

    Raises:
        ValueError: If the method identifier is not a known proposal rule.
    """
    if method == METHOD_MAX_PLUS_SIGMA:
        return propose_max_plus_sigma(stats)
    if method == METHOD_NOMINAL_SCALED:
        return propose_nominal_scaled(stats, nominal_scale)
    raise ValueError(f"unknown proposal method {method!r}")


def _verify_one(capture: dict[str, Any]) -> RealCalibrationVerification:
    """Re-run the calibration pipeline over one real residual capture.

    Args:
        capture: One parsed capture record.

    Returns:
        (RealCalibrationVerification) The verdict; calibration set only when the capture
        parsed and produced a proposal.
    """
    trajectory_id = str(capture.get("trajectory_id", ""))
    try:
        collector = collector_for_arm()
        for run in capture["runs"]:
            collector.add_run(np.asarray(run, dtype=np.float64))
        stats = collector.stats()
        method = str(capture["method"])
        nominal_scale = float(capture.get("nominal_scale", NOMINAL_SCALE_DEFAULT))
        proposal = _proposal_for(method, stats, nominal_scale)
        judgment = NoCollisionJudgment(
            operator=str(capture["operator"]),
            trajectory_id=trajectory_id,
            attested=bool(capture["attested"]),
            note=str(capture.get("note", "")),
        )
    except Exception as refusal:  # noqa: BLE001 — the refusal reason is the reported verdict
        return RealCalibrationVerification(
            trajectory_id=trajectory_id, calibration=None, refusal=str(refusal)
        )
    return RealCalibrationVerification(
        trajectory_id=trajectory_id,
        calibration=attested_calibration(proposal, judgment),
        refusal="",
    )


def reverify_from_fixture(fixture_dir: Path) -> list[RealCalibrationVerification]:
    """Re-run the calibration pipeline against real collision-free residual captures.

    Loads every `*.json` capture in the directory and re-applies the identical
    collector-proposer-bounds pipeline the offline tests exercise, now over real residuals,
    stamping canon only where the operator attested no collision. This is the
    re-verification the deferred calibration run requires.

    Args:
        fixture_dir: Directory of captured residual JSON files, one per trajectory.

    Returns:
        (list[RealCalibrationVerification]) One verification per capture, ordered by filename.

    Raises:
        FileNotFoundError: If the directory holds no `*.json` capture.
    """
    capture_files = sorted(fixture_dir.glob("*.json"))
    if not capture_files:
        raise FileNotFoundError(f"no *.json residual capture in {fixture_dir}")
    return [_verify_one(json.loads(path.read_text(encoding="utf-8"))) for path in capture_files]
