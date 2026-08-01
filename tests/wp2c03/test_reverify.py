"""The calibration run: deferred until a real capture is named, then actually run (WP-2C-03).

The real calibration run needs a powered arm, WP-2C-01's live residual and an operator
watching for contact, none of which a desktop has, so it is skipped with a reason and never
asserted green from nothing. It stops being deferred the moment `FIXTURE_ENV_VAR` names a
capture directory: the acceptance then runs over those bytes and can fail. The remaining
tests exercise the same hook on synthetic captures — canon only on an operator attestation,
the physics floor read from WP-1-06 rather than the capture, a malformed capture refused.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pytest

from backend.safety_bringup.thresholds import floor_for_joint
from backend.threshold_calib import (
    FIXTURE_ENV_VAR,
    METHOD_MAX_PLUS_SIGMA,
    fixture_dir_from_env,
    reverify_from_fixture,
    synthetic_residual_run,
)

_ARM_JOINTS = 7

# Read once, at collection: the operator supplies the directory on the pytest command line,
# so the skip decision and the assertion below must see the same value. The skip turns on the
# raw string rather than the resolved directory — a mistyped path is a typo to report, not a
# deferral to honour, and resolving first would silently turn it back into a skip.
_FIXTURE_ENV_RAW = os.environ.get(FIXTURE_ENV_VAR, "")

_DEFERRED_REASON = (
    "threshold calibration requires a real collision-free run under WP-2C-01's live residual "
    f"with an operator attesting no contact; set {FIXTURE_ENV_VAR} to that capture directory "
    "to run the acceptance here — never asserted green without one (02a §4.1)"
)


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


@pytest.mark.skipif(not _FIXTURE_ENV_RAW, reason=_DEFERRED_REASON)
def test_calibration_run_against_the_real_fixture() -> None:
    # The deferred acceptance itself, run over the operator's captures. Every capture must
    # be attested and produce canon for all seven joints at or above the physics floor; a
    # capture the pipeline refused is a failure here, not a silent omission.
    fixture_dir = fixture_dir_from_env()
    assert fixture_dir is not None, (
        f"{FIXTURE_ENV_VAR} names {_FIXTURE_ENV_RAW!r}, which is not a directory"
    )
    verifications = reverify_from_fixture(fixture_dir)
    assert verifications, f"no residual capture in {fixture_dir}"
    for verification in verifications:
        assert not verification.refusal, (
            f"capture {verification.trajectory_id!r} refused: {verification.refusal}"
        )
        calibration = verification.calibration
        assert calibration is not None
        assert calibration.canonical, (
            f"capture {verification.trajectory_id!r} produced no canon: the operator did not "
            "attest the run collision-free"
        )
        assert len(calibration.require_canonical()) == _ARM_JOINTS
        for joint in calibration.proposal.per_joint:
            assert joint.effective_nm >= floor_for_joint(joint.joint_index)


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
