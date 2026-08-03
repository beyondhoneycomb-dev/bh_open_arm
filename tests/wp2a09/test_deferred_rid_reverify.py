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

The set a capture is judged complete against is the fitted one. A build whose tool has no
motor on `0x08` produces a seven-motor capture, and the two tests below pin both halves of
that: such a capture clears the gate, and one short of a *fitted* motor still blocks.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.can.rid.registers import RID_TMAX
from backend.can.rid.reverify import (
    DEFAULT_MARGIN_LSB,
    assert_every_arm_answered,
    reverify_from_fixture,
)
from backend.endeffector import GRIPPER_SEND_ID, default_profile, gripper_build, spatula_build
from backend.preflight.reverify import (
    FIXTURE_ENV_VAR,
    fixture_dir_from_env,
    reverify_rid_crosscheck,
)
from tests.wp2a09.builders import capture_dict

_REAL_FIXTURE = fixture_dir_from_env()
_DM4340_JOINT = 0x03
_FITTED_SEND_IDS = default_profile().motor_send_ids

# Taken from the tool registry rather than the ambient rig file: the seven-vs-eight distinction
# the pass-through tests turn on has to survive a refit of the bench.
_SPATULA_SEND_IDS = spatula_build().motor_send_ids
_GRIPPER_SEND_IDS = gripper_build().motor_send_ids


def _write_capture(directory: Path, name: str, capture: dict[str, object]) -> None:
    """Write one capture JSON into a directory in the schema the hook loads."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(json.dumps(capture), encoding="utf-8")


@pytest.mark.skipif(
    _REAL_FIXTURE is None,
    reason=(
        "live RID cross-check needs every fitted motor of both arms powered — seven per arm on "
        f"the spatula build, nothing on 0x08; set {FIXTURE_ENV_VAR} to a real capture directory "
        "holding one dump per arm to re-run the deferred acceptance on hardware"
    ),
)
def test_live_rid_crosscheck_against_real_capture() -> None:
    # Runs only when a real capture directory is supplied. Every interface's real read must
    # clear the RID torque gate for torque-ON to be permitted — and "every" is the rig's arms,
    # not whichever arms the directory happens to hold. Each dump is judged on its own, so a
    # capture of one arm clears this while the other went unread: seven motors of fourteen,
    # every verdict in the seven passing.
    assert _REAL_FIXTURE is not None
    assert_every_arm_answered(reverify_from_fixture(_REAL_FIXTURE, DEFAULT_MARGIN_LSB))
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


def test_hook_passes_on_a_capture_holding_only_the_fitted_motors(tmp_path: Path) -> None:
    # The rig's tool puts no motor on 0x08, so its capture holds seven. The gate judges
    # completeness against the fitted set, not the eight-motor registration.
    _write_capture(tmp_path, "can0.json", capture_dict(send_ids=_FITTED_SEND_IDS))
    results = reverify_rid_crosscheck(tmp_path)
    assert results[0].passed, results[0].detail


def test_hook_blocks_when_a_fitted_motor_is_absent(tmp_path: Path) -> None:
    # Narrowing the expected set to the fitted one must not narrow it further: a capture
    # short of a motor the arm does carry is still the partial read that forbids torque-ON.
    absent = _FITTED_SEND_IDS[-1]
    _write_capture(tmp_path, "can0.json", capture_dict(send_ids=_FITTED_SEND_IDS[:-1]))
    results = reverify_rid_crosscheck(tmp_path)
    assert not results[0].passed
    assert f"0x{absent:02x}" in results[0].detail


def test_the_gate_judges_the_motor_ids_the_caller_named(tmp_path: Path) -> None:
    # A caller that states the set gets that set judged. Drop the argument on the way to the
    # judgment and this capture clears the gate, because the bench's own fitted set is exactly
    # what it holds — the one arrangement in which discarding the caller looks like agreement.
    _write_capture(tmp_path, "can0.json", capture_dict(send_ids=_SPATULA_SEND_IDS))
    results = reverify_rid_crosscheck(tmp_path, expected_motor_ids=_GRIPPER_SEND_IDS)
    assert not results[0].passed
    assert f"0x{GRIPPER_SEND_ID:02x}" in results[0].detail


def test_both_reverify_hooks_default_to_the_same_expected_set(tmp_path: Path) -> None:
    # Two hooks read the same capture directory, and neither caller names a set. They must not
    # answer "which motors must answer" differently: one gate permitting torque-ON off a capture
    # the other calls a partial read is a disagreement the operator would never see stated.
    _write_capture(tmp_path, "can0.json", capture_dict(send_ids=_FITTED_SEND_IDS))
    assert reverify_rid_crosscheck(tmp_path)[0].passed
    judged = reverify_from_fixture(tmp_path, DEFAULT_MARGIN_LSB)[0].rid9
    assert judged.missing_motor_ids == ()
    assert tuple(motor.motor_id for motor in judged.per_motor) == tuple(_FITTED_SEND_IDS)
