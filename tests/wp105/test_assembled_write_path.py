"""What the assembled write path actually put on the bus, judged on real numbers.

The join between the enforcement point and the single writer is proved offline against a fake
CAN writer (`tests/wp103/test_gateway_write_path_assembly.py`). What no offline run can show is
that the frame the writer put on can0/can1 held the seven fitted motors where they already
were. That needs the arm powered, a real adapter and a PG-SAFE-001 PASS, and this host has none
of the three — so it is deferred to a real capture and judged there by the same production
rules the offline engage is judged by: `assert_targets_are_present_pose` for the angles and
`assert_safe_hold` for the stiffness.

A real capture must carry the pose the arm reported and the frame the writer emitted for a
command the filter refused. One that carries neither fails here. Passing on an absent block
would turn the deferral into a claim that a run nobody made came back clean, and the deferred
E-Stop acceptance beside it already refuses to work that way.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from backend.torque_bringup import (
    SafeHoldViolationError,
    TorqueEngageSequenceError,
    assert_safe_hold,
    assert_targets_are_present_pose,
)
from backend.torque_bringup.reverify import fixture_dir_from_env
from contracts.action import ExecutedMitCommand
from contracts.units import Nm, Rad, RadPerSec
from tests.wp105.conftest import POSE_STEP_RAD

_REAL_FIXTURE = fixture_dir_from_env()
_SKIP_REASON = (
    "the frame the single writer put on the bus for a refused command: requires the arm "
    "powered, a real CAN adapter and a PG-SAFE-001 PASS (12 FR-SAF-075, 16 M-2); set "
    "OPENARM_TORQUE_BRINGUP_REAL_FIXTURE to a real capture directory to re-verify"
)

# The capture block this judgment reads. Named once, so the schema the synthetic captures write
# and the schema the real one is read from cannot drift apart inside this file.
WRITE_BLOCK = "assembled_write"
PRESENT_KEY = "present_pose_rad"
FRAME_KEY = "refused_frame"

# How far a drifted frame commands away from the pose the arm reported. Any non-zero value
# fails the judgment; this one is far enough to be unmistakable in the failure message.
DRIFT_RAD = 0.2

# Gains a captured hold frame carries. These stand in for whatever the rig recorded — the
# judgment reads them off the capture rather than recomputing them, so a synthetic value here
# is only the input to the check, never the thing being asserted.
CAPTURED_KP = 40.0
CAPTURED_KD = 1.0
LIMP_KP = 0.0
CAPTURED_DQ_RAD_S = 0.0
CAPTURED_TAU_NM = 0.0

# Fitted motor count on this rig: the spatula build, seven motors and nothing on 0x08.
FITTED_JOINTS = 7


class AssembledWriteMissingError(AssertionError):
    """Raised when a capture carries no record of what the single writer emitted.

    An `AssertionError` deliberately: a supplied capture that cannot answer the question is a
    failed acceptance, not a configuration problem to skip over.
    """


def _synthetic_capture(drift_rad: float = 0.0, kp: float = CAPTURED_KP) -> dict[str, Any]:
    """Build one capture record carrying an assembled-write block.

    Args:
        drift_rad: How far the emitted frame commands away from the reported pose.
        kp: The stiffness the emitted frame carried.

    Returns:
        (dict[str, Any]) The capture record.
    """
    present = [POSE_STEP_RAD * index for index in range(FITTED_JOINTS)]
    return {
        WRITE_BLOCK: {
            PRESENT_KEY: present,
            FRAME_KEY: [
                {
                    "kp": kp,
                    "kd": CAPTURED_KD,
                    "q": angle + drift_rad,
                    "dq": CAPTURED_DQ_RAD_S,
                    "tau": CAPTURED_TAU_NM,
                }
                for angle in present
            ],
        }
    }


def _capture_dir(root: Path, capture: dict[str, Any]) -> Path:
    """Write one capture record into a fresh directory.

    Args:
        root: Directory to write into.
        capture: The record to write.

    Returns:
        (Path) The directory holding the capture.
    """
    (root / "host.json").write_text(json.dumps(capture), encoding="utf-8")
    return root


def read_assembled_write(
    capture: dict[str, Any],
) -> tuple[tuple[ExecutedMitCommand, ...], tuple[Rad, ...]]:
    """Read the emitted frame and the reported pose out of one capture record.

    Args:
        capture: One parsed capture record.

    Returns:
        (tuple) The frame the single writer emitted, and the pose the arm reported.

    Raises:
        AssembledWriteMissingError: If the record carries no assembled-write block, or the
            block is missing either half of the comparison.
    """
    block = capture.get(WRITE_BLOCK)
    if not isinstance(block, dict) or PRESENT_KEY not in block or FRAME_KEY not in block:
        raise AssembledWriteMissingError(
            f"the capture carries no {WRITE_BLOCK!r} block with both {PRESENT_KEY!r} and "
            f"{FRAME_KEY!r}; the frame the single writer emitted for a refused command is the "
            "whole measurement, and a capture without it answers nothing"
        )
    present = tuple(Rad(float(angle)) for angle in block[PRESENT_KEY])
    frame = tuple(
        ExecutedMitCommand(
            kp=float(command["kp"]),
            kd=float(command["kd"]),
            q=Rad(float(command["q"])),
            dq=RadPerSec(float(command["dq"])),
            tau=Nm(float(command["tau"])),
        )
        for command in block[FRAME_KEY]
    )
    return frame, present


def judge_assembled_write(capture: dict[str, Any]) -> None:
    """Run both production judgments over one capture's assembled-write record.

    Args:
        capture: One parsed capture record.

    Raises:
        AssembledWriteMissingError: If the record carries no assembled-write block.
        TorqueEngageSequenceError: If the emitted frame left the reported pose.
        SafeHoldViolationError: If the emitted frame commanded no restoring stiffness.
    """
    frame, present = read_assembled_write(capture)
    assert_safe_hold(frame)
    assert_targets_are_present_pose(frame, present)


def test_a_frame_that_left_the_present_pose_is_flagged(tmp_path: Path) -> None:
    """A refused command whose emitted frame moved is the failure this measurement looks for.

    On a brakeless arm a hold aimed at a pose the arm is not at snaps it there the moment
    torque comes on, so a drifted frame has to fail even though it is a perfectly valid MIT
    command.
    """
    capture_dir = _capture_dir(tmp_path, _synthetic_capture(drift_rad=DRIFT_RAD))
    capture = json.loads((capture_dir / "host.json").read_text(encoding="utf-8"))

    with pytest.raises(TorqueEngageSequenceError):
        judge_assembled_write(capture)


def test_a_limp_frame_is_flagged(tmp_path: Path) -> None:
    """A frame at the reported pose but with no stiffness is a drop wearing a hold's angles."""
    capture_dir = _capture_dir(tmp_path, _synthetic_capture(kp=LIMP_KP))
    capture = json.loads((capture_dir / "host.json").read_text(encoding="utf-8"))

    with pytest.raises(SafeHoldViolationError):
        judge_assembled_write(capture)


def test_a_frame_held_at_the_present_pose_passes(tmp_path: Path) -> None:
    """The judgment admits the frame a correctly assembled refusal produces."""
    capture_dir = _capture_dir(tmp_path, _synthetic_capture())
    capture = json.loads((capture_dir / "host.json").read_text(encoding="utf-8"))

    judge_assembled_write(capture)


def test_a_capture_with_no_assembled_write_block_fails(tmp_path: Path) -> None:
    """Silence is the failing side: a capture that never recorded the frame answers nothing."""
    capture_dir = _capture_dir(tmp_path, {"host_id": "synthetic-host"})
    capture = json.loads((capture_dir / "host.json").read_text(encoding="utf-8"))

    with pytest.raises(AssembledWriteMissingError):
        judge_assembled_write(capture)


@pytest.mark.skipif(_REAL_FIXTURE is None, reason=_SKIP_REASON)
def test_deferred_real_assembled_write_holds_at_present() -> None:
    # The offline join runs on a fake writer, so nothing here has yet been on a bus. This is
    # where the real frame is judged, by the same two production rules the synthetic captures
    # above prove bite.
    assert _REAL_FIXTURE is not None
    for path in sorted(_REAL_FIXTURE.glob("*.json")):
        judge_assembled_write(json.loads(path.read_text(encoding="utf-8")))
