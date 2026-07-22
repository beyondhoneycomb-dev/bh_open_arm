"""The deferred item: the LIVE RID cross-check (real sixteen motors). SKIP + hook proof.

The RID torque gate runs here on synthetic reads (test_rid_crosscheck); what cannot run
here is the *live* read — sixteen powered motors with torque OFF asserted first
(`12` FR-SAF-075), of which this host has none. That acceptance is SKIPPED WITH A REASON,
never asserted green, and wired to `backend.preflight.reverify`, which re-runs the exact
gate against a real capture directory named by `OPENARM_RID_REAL_FIXTURE` (plan 02a §4.1).

To prove the hook is real and not a stub, the hook-proof tests build a capture directory
in the real `dump.py` schema and run `reverify_rid_crosscheck` end to end. That exercises
the plumbing without pretending to reach hardware; the hardware truth stays in the skipped
test.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.can.rid.registers import RID_TMAX
from backend.preflight.reverify import (
    FIXTURE_ENV_VAR,
    fixture_dir_from_env,
    reverify_rid_crosscheck,
)
from tests.wp2a09.builders import capture_dict

_REAL_FIXTURE = fixture_dir_from_env()
_DM4340_JOINT = 0x03


def _write_capture(directory: Path, name: str, capture: dict[str, object]) -> None:
    """Write one capture JSON into a directory in the schema the hook loads."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(json.dumps(capture), encoding="utf-8")


@pytest.mark.skipif(
    _REAL_FIXTURE is None,
    reason=(
        f"live RID cross-check needs 16 powered motors; set {FIXTURE_ENV_VAR} to a real "
        "capture directory to re-run the deferred acceptance on hardware"
    ),
)
def test_live_rid_crosscheck_against_real_capture() -> None:
    # Runs only when a real capture directory is supplied. Every interface's real read
    # must clear the RID torque gate for torque-ON to be permitted.
    assert _REAL_FIXTURE is not None
    results = reverify_rid_crosscheck(_REAL_FIXTURE)
    assert results
    assert all(result.passed for result in results)


def test_hook_passes_on_matching_capture(tmp_path: Path) -> None:
    _write_capture(tmp_path, "oa_fl.json", capture_dict())
    results = reverify_rid_crosscheck(tmp_path)
    assert len(results) == 1
    assert results[0].passed


def test_hook_blocks_on_mismatching_capture(tmp_path: Path) -> None:
    _write_capture(
        tmp_path,
        "oa_fl.json",
        capture_dict(break_motor=_DM4340_JOINT, break_rid=RID_TMAX, break_value=5.0),
    )
    results = reverify_rid_crosscheck(tmp_path)
    assert not results[0].passed
