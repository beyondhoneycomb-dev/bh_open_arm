"""Real-fixture re-verification hook for the deferred RID acceptances (plan 02a §4.1).

Most of this WP runs here: the decoder, the limit comparison (③), the type-misread
check (⑦) and the write-symbol static check (⑧) need no motors. What does not run
here is every acceptance that needs the powered motors themselves — the RID 9 read
of every fitted motor (①), its branch judgment (②), J7's RID 23 (④), a DM4340's
RID 22 (⑤), and the UV/OT/OC/OV record (⑥) — because those need real motors, real
power, and a torque-OFF assertion first (`12` FR-SAF-075), none of which exist on
this host. They are deferred, but not asserted green and not dropped.

How many motors that is comes from the fitted tool, never from the eight-motor
registration. The bench runs a fixed spatula: seven per arm, nothing on `0x08`.
Judging seven against eight reports the absent motor as one that failed to answer —
a fact about the build, dressed as a fault.

This is the hook the deferral is required to ship. The moment a directory of real
captures is supplied, `reverify_from_fixture` re-runs `evaluate_dump` — the identical
judgment the synthetic tests run — against the real bytes. Until then the bound test
skips with a reason. The directory holds one dump JSON per interface (the `dump.py`
schema, faithfully the four little-endian value bytes per RID).

A capture directory is one interface per arm, and which interfaces those are is the
operator's persisted answer rather than anything the bytes carry. So the count of
files is not the count of arms: two dumps taken from the same channel are two files
and one arm, and on a bimanual rig that is half a read passing as a whole one.
`assert_every_arm_answered` is what separates them.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path

from backend.can.rid.dump import load_dump
from backend.can.rid.evaluate import DumpEvaluation, evaluate_dump
from backend.endeffector import SIDES


class ArmCoverageError(Exception):
    """Raised when a capture directory does not cover every arm the rig declares.

    Separate from a judgment failure: nothing in the dumps is wrong, there are just not
    enough of them. A half-read rig whose one capture is clean is the shape most likely to
    be mistaken for a whole one, because every per-motor verdict in it passes.
    """


# Environment variable a caller sets to point the hook at a real capture directory.
FIXTURE_ENV_VAR = "OPENARM_RID_REAL_FIXTURE"

# Default RID 9 send-period margin, in 50 us LSBs, used when re-running the timeout
# branch against a real capture. A real run overrides it with the measured Cat-2
# hold send period (`12` NFR-SAF-007); this is only the placeholder for the shape.
DEFAULT_MARGIN_LSB = 20


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


def reverify_from_fixture(
    fixture_dir: Path,
    margin_lsb: int = DEFAULT_MARGIN_LSB,
    expected_motor_ids: Sequence[int] | None = None,
) -> list[DumpEvaluation]:
    """Re-run the full RID judgment against real captured dumps.

    Loads every `*.json` dump in the directory and runs `evaluate_dump` on each —
    the same decode, RID 9 branch, RID 21/22/23 comparison, J7 and VMAX judgments,
    and protection record that the synthetic tests exercise, now pointed at real
    bytes. This is the re-verification the deferred acceptances (①②④⑤⑥) require.

    Args:
        fixture_dir: Directory of captured dump JSON files, one per interface.
        margin_lsb: RID 9 send-period margin in 50 us LSBs for the timeout branch.
        expected_motor_ids: The motors the arm actually has. Passed through to
            `evaluate_dump`, which defaults it to the ids the fitted tool puts on the bus
            (`default_profile().motor_send_ids`) — the same default the WP-2A-09 torque gate
            applies, so both hooks answer "which motors must answer" identically. Observed on
            this bench: judged against the eight-motor registration, the absent `0x08` is
            reported as a motor that failed to answer, on every channel, forever.

    Returns:
        (list[DumpEvaluation]) One evaluation per capture file, ordered by filename.

    Raises:
        FileNotFoundError: If the directory holds no `*.json` capture.
    """
    dump_files = sorted(fixture_dir.glob("*.json"))
    if not dump_files:
        raise FileNotFoundError(f"no *.json RID capture in {fixture_dir}")
    return [evaluate_dump(load_dump(path), margin_lsb, expected_motor_ids) for path in dump_files]


def assert_every_arm_answered(
    evaluations: Sequence[DumpEvaluation], arm_count: int = len(SIDES)
) -> None:
    """Refuse a capture set that does not hold one distinct interface per arm.

    The per-motor judgments cannot see this. Each dump is judged on its own, so a directory
    holding one arm's capture — or the same arm's capture twice under two filenames — clears
    every acceptance in it while half the rig went unread. On a bimanual arm that is seven
    motors of fourteen, and the acceptances it clears are the ones whose text says every
    fitted motor answered.

    The interface *names* are not checked, because they are not knowable from a capture taken
    on another day: the persisted binding keys each arm by `ID_PATH` and `dev_id`, and the
    `canN` name is resolved against the live channels. What is checkable offline is that as
    many distinct interfaces answered as the rig has arms, and that none answered twice.

    Args:
        evaluations: The per-file evaluations, as `reverify_from_fixture` returned them.
        arm_count: How many arms the rig carries. Defaults to the frozen bimanual pair.

    Raises:
        ArmCoverageError: If two dumps report the same interface, or fewer distinct
            interfaces answered than the rig has arms.
    """
    seen = [evaluation.iface for evaluation in evaluations]
    duplicated = sorted({iface for iface in seen if seen.count(iface) > 1})
    if duplicated:
        raise ArmCoverageError(
            f"the capture set reports interface {duplicated} more than once: {sorted(seen)}. "
            "Two dumps from one channel are two files and one arm, and every per-motor verdict "
            "in them passes while the other arm went unread"
        )
    if len(set(seen)) < arm_count:
        raise ArmCoverageError(
            f"the capture set holds {len(set(seen))} interface(s) {sorted(seen)} for a rig with "
            f"{arm_count} arm(s). Every motor in what was captured can pass while an arm was "
            "never read — the acceptance says every fitted motor, not every captured one"
        )
