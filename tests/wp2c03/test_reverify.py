"""The deferred calibration run (phase 2) — skipped with a reason, re-run by hook (WP-2C-03).

The real calibration run needs a powered arm, WP-2C-01's live residual and an operator
watching for contact, and cannot run on this host: no CAN, no motor, no operator. It is
deferred — never asserted green. What is tested here is the re-verification hook: given a
real collision-free residual capture it re-runs the identical collector-proposer-bounds
pipeline, stamps canon only when the operator attested no collision, and reads the physics
floor from WP-1-06 rather than the capture — so the hook can neither self-approve an
unattested run nor accept a threshold below noise, the two ways THE ONE RULE could be broken.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from backend.safety_bringup.thresholds import floor_for_joint
from backend.threshold_calib import (
    METHOD_MAX_PLUS_SIGMA,
    fixture_dir_from_env,
    reverify_from_fixture,
    synthetic_residual_run,
)

_ARM_JOINTS = 7


def _capture(
    directory: Path,
    name: str,
    *,
    runs: list[list[list[float]]],
    attested: bool,
    method: str = METHOD_MAX_PLUS_SIGMA,
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    body = {
        "trajectory_id": name,
        "operator": "operator-1",
        "attested": attested,
        "note": "",
        "method": method,
        "runs": runs,
    }
    (directory / f"{name}.json").write_text(json.dumps(body), encoding="utf-8")


def _real_runs() -> list[list[list[float]]]:
    return [synthetic_residual_run(i).tolist() for i in range(3)]


def test_calibration_run_deferred_without_real_fixture() -> None:
    # Phase 2: with no fixture directory the real calibration run is deferred, not asserted.
    if fixture_dir_from_env() is not None:
        pytest.skip("real fixture present; the deferred path is not exercised")
    pytest.skip(
        "threshold calibration requires a real collision-free run under WP-2C-01's live "
        "residual with an operator attesting no contact; deferred to the real fixture via "
        "OPENARM_THRESHOLD_CALIB_REAL_FIXTURE — never asserted green here (02a §4.1)"
    )


def test_hook_stamps_canon_on_attested_capture(tmp_path: Path) -> None:
    _capture(tmp_path, "sweep-A", runs=_real_runs(), attested=True)
    results = reverify_from_fixture(tmp_path)
    assert len(results) == 1
    verification = results[0]
    assert verification.calibration is not None
    assert verification.calibration.canonical
    assert len(verification.calibration.require_canonical()) == _ARM_JOINTS


def test_hook_refuses_canon_on_unattested_capture(tmp_path: Path) -> None:
    # An unattested run is recorded but never canon — the hook cannot self-approve.
    _capture(tmp_path, "sweep-B", runs=_real_runs(), attested=False)
    verification = reverify_from_fixture(tmp_path)[0]
    assert verification.calibration is not None
    assert not verification.calibration.canonical


def test_hook_reads_floor_from_physics_not_capture(tmp_path: Path) -> None:
    # A capture of near-zero residual proposes below the floor; the hook raises it to the
    # physics floor read from WP-1-06, so the capture cannot lower the threshold.
    tiny = (np.zeros((50, _ARM_JOINTS)) + 0.001).tolist()
    _capture(tmp_path, "tiny", runs=[tiny, tiny], attested=True)
    calibration = reverify_from_fixture(tmp_path)[0].calibration
    assert calibration is not None
    for joint in calibration.proposal.per_joint:
        assert joint.floor_clamped
        assert joint.effective_nm == pytest.approx(floor_for_joint(joint.joint_index))


def test_hook_refuses_malformed_capture(tmp_path: Path) -> None:
    # A single-run capture cannot support a sigma; it is refused with a reason, not stamped.
    _capture(tmp_path, "one-run", runs=[synthetic_residual_run(0).tolist()], attested=True)
    verification = reverify_from_fixture(tmp_path)[0]
    assert verification.calibration is None
    assert verification.refusal


def test_hook_raises_on_empty_fixture_dir(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="no .* residual capture"):
        reverify_from_fixture(tmp_path)
