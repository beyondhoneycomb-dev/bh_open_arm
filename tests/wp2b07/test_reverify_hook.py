"""The deferred real PG-FRIC-001 pass: SKIPPED with a reason, plus a proof the hook is real.

The live re-verification needs real excitation captures (WP-2B-06 on hardware) and a PG-J7-001
torque-scale pass, which this host cannot produce. That acceptance is skipped with a reason,
never asserted green. The hook-proof tests build a capture directory in the schema the hook
loads and run `reverify_from_fixture` end to end, exercising the plumbing without pretending to
reach hardware — the hardware truth stays in the skipped test.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.friction import SyntheticLog, reverify_from_fixture
from backend.friction.reverify import fixture_dir_from_env

_REAL_FIXTURE = fixture_dir_from_env()


def _write_capture(directory: Path, name: str, log: SyntheticLog) -> None:
    """Write one excitation capture JSON in the schema the hook loads."""
    directory.mkdir(parents=True, exist_ok=True)
    capture = {
        "log_freq_hz": log.log.log_freq_hz,
        "q": log.log.q.tolist(),
        "qd": log.log.qd.tolist(),
        "qdd": log.log.qdd.tolist(),
        "tau": log.log.tau.tolist(),
    }
    (directory / name).write_text(json.dumps(capture), encoding="utf-8")


@pytest.mark.skipif(
    _REAL_FIXTURE is None,
    reason=(
        "real PG-FRIC-001 pass needs real excitation logs (WP-2B-06 on hardware) and a "
        "PG-J7-001 torque-scale pass; set OPENARM_FRICTION_REAL_FIXTURE to a real capture "
        "directory to re-run the deferred acceptance on hardware"
    ),
)
def test_live_reverify_against_real_captures() -> None:
    # Runs only when a real capture directory is supplied. The identical fit and separation the
    # offline path uses are re-run against real numbers.
    assert _REAL_FIXTURE is not None
    results = reverify_from_fixture(_REAL_FIXTURE)
    assert results
    assert all(verification.all_converged for verification in results)


def test_hook_runs_the_identical_fit_on_a_capture(tmp_path: Path, synthetic: SyntheticLog) -> None:
    _write_capture(tmp_path, "session_a.json", synthetic)
    results = reverify_from_fixture(tmp_path)
    assert len(results) == 1
    verification = results[0]
    assert verification.all_converged
    assert verification.all_separated
    assert len(verification.per_joint_separated) == 7


def test_hook_reports_the_external_torque_scale_precondition(
    tmp_path: Path, synthetic: SyntheticLog
) -> None:
    _write_capture(tmp_path, "session_a.json", synthetic)
    verification = reverify_from_fixture(tmp_path)[0]
    assert "PG-J7-001" in verification.torque_scale_precondition


def test_hook_refuses_an_empty_directory(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        reverify_from_fixture(tmp_path)
