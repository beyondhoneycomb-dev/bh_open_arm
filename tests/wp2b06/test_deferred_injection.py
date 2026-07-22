"""The deferred item: the real torque-ON injection on the arm. SKIP + reverify-hook proof.

The trajectory design, the three hard gates, the four abort causes, and resume-by-index
all run offline (the other WP-2B-06 tests). What cannot run here is the actual injection —
torque-ON on a 40 Nm brakeless arm, with an `FR-MOT-058` torque path, real motors, and a
supervising operator, none of which this host has. That acceptance is SKIPPED WITH A
REASON, never asserted green (a faked injection green is a safety lie the friction fit and
every detector would trust), and wired to `reverify_injection_sessions`, which re-checks a
real capture's safety invariants.

To prove the hook is real and not a stub, the hook-proof tests build recorded sessions in
the capture schema and run the hook end to end — a clean capture passes, and each way a
capture can lie fails the matching invariant.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from backend.excitation.reverify import (
    FIXTURE_ENV_VAR,
    ReverifyResult,
    fixture_dir_from_env,
    reverify_injection_sessions,
)

_REAL_FIXTURE = fixture_dir_from_env()

_ABORTED_FIRST_SEGMENT = {
    "start_index": 0,
    "commanded_indices": [0, 1, 2],
    "abort": {"index": 3, "cause": "human_abort"},
}
_CLEAN_SESSION: dict[str, Any] = {
    "torque_path_present": True,
    "dry_run_armed": True,
    "safe_state_confirmed": True,
    "segments": [
        _ABORTED_FIRST_SEGMENT,
        {"start_index": 3, "commanded_indices": [3, 4, 5, 6], "abort": None},
    ],
}


def _write_session(directory: Path, name: str, session: dict[str, Any]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(json.dumps(session), encoding="utf-8")


def _check(results: list[ReverifyResult], name: str) -> ReverifyResult:
    return next(result for result in results if result.check == name)


@pytest.mark.skip(
    reason=(
        "HW-DEFERRED: the real exciting-trajectory injection is torque-ON on a 40 Nm "
        "brakeless arm and needs the FR-MOT-058 torque path, real motors, and an operator, "
        "none present on this host. Re-verify a real capture with "
        f"reverify_injection_sessions() on a directory named by {FIXTURE_ENV_VAR}. Never "
        "asserted offline — a faked injection green is a safety lie."
    )
)
def test_real_arm_injection_deferred() -> None:
    """Deferred: the torque-ON injection on the real arm."""
    raise AssertionError("must run on a real fixture; this body must never execute here")


@pytest.mark.skipif(
    _REAL_FIXTURE is None,
    reason=(
        f"real injection re-verification needs a capture; set {FIXTURE_ENV_VAR} to a "
        "recorded-session directory to re-run the deferred acceptance on hardware evidence"
    ),
)
def test_reverify_real_capture() -> None:
    assert _REAL_FIXTURE is not None
    results = reverify_injection_sessions(_REAL_FIXTURE)
    assert results
    assert all(result.passed for result in results)


def test_hook_passes_on_a_clean_capture(tmp_path: Path) -> None:
    _write_session(tmp_path, "session.json", _CLEAN_SESSION)
    results = reverify_injection_sessions(tmp_path)
    assert all(result.passed for result in results)


def test_hook_fails_when_a_gate_was_not_held(tmp_path: Path) -> None:
    _write_session(tmp_path, "session.json", {**_CLEAN_SESSION, "torque_path_present": False})
    results = reverify_injection_sessions(tmp_path)
    assert _check(results, "preconditions_held").passed is False


def test_hook_fails_when_an_abort_did_not_stop_injection(tmp_path: Path) -> None:
    # A capture claiming a command at the abort tick means the abort did not bite.
    session = {
        **_CLEAN_SESSION,
        "segments": [
            {"start_index": 0, "commanded_indices": [0, 1, 2, 3], "abort": {"index": 3}},
            {"start_index": 3, "commanded_indices": [3, 4], "abort": None},
        ],
    }
    _write_session(tmp_path, "session.json", session)
    results = reverify_injection_sessions(tmp_path)
    assert _check(results, "abort_stopped_injection").passed is False


def test_hook_fails_when_resume_index_does_not_match(tmp_path: Path) -> None:
    session = {
        **_CLEAN_SESSION,
        "segments": [
            {"start_index": 0, "commanded_indices": [0, 1, 2], "abort": {"index": 3}},
            {"start_index": 5, "commanded_indices": [5, 6], "abort": None},
        ],
    }
    _write_session(tmp_path, "session.json", session)
    results = reverify_injection_sessions(tmp_path)
    assert _check(results, "resume_by_index").passed is False


def test_hook_fails_on_a_non_contiguous_drive(tmp_path: Path) -> None:
    session = {
        **_CLEAN_SESSION,
        "segments": [{"start_index": 0, "commanded_indices": [0, 1, 3], "abort": None}],
    }
    _write_session(tmp_path, "session.json", session)
    results = reverify_injection_sessions(tmp_path)
    assert _check(results, "segments_contiguous").passed is False


def test_hook_refuses_an_empty_fixture(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        reverify_injection_sessions(tmp_path)
