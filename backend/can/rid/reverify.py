"""Real-fixture re-verification hook for the deferred RID acceptances (plan 02a §4.1).

Most of this WP runs here: the decoder, the limit comparison (③), the type-misread
check (⑦) and the write-symbol static check (⑧) need no motors. What does not run
here is every acceptance that needs the 16 powered motors themselves — the RID 9
read of all 16 (①), its branch judgment (②), J7's RID 23 (④), a DM4340's RID 22
(⑤), and the 8-motor UV/OT/OC/OV record (⑥) — because those need real motors, real
power, and a torque-OFF assertion first (`12` FR-SAF-075), none of which exist on
this host. They are deferred, but not asserted green and not dropped.

This is the hook the deferral is required to ship. The moment a directory of real
16-motor captures is supplied, `reverify_from_fixture` re-runs `evaluate_dump` — the
identical judgment the synthetic tests run — against the real bytes. Until then the
bound test skips with a reason. The directory holds one dump JSON per interface (the
`dump.py` schema, faithfully the four little-endian value bytes per RID).
"""

from __future__ import annotations

import os
from pathlib import Path

from backend.can.rid.dump import load_dump
from backend.can.rid.evaluate import DumpEvaluation, evaluate_dump

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
    fixture_dir: Path, margin_lsb: int = DEFAULT_MARGIN_LSB
) -> list[DumpEvaluation]:
    """Re-run the full RID judgment against real captured dumps.

    Loads every `*.json` dump in the directory and runs `evaluate_dump` on each —
    the same decode, RID 9 branch, RID 21/22/23 comparison, J7 and VMAX judgments,
    and protection record that the synthetic tests exercise, now pointed at real
    bytes. This is the re-verification the deferred acceptances (①②④⑤⑥) require.

    Args:
        fixture_dir: Directory of captured dump JSON files, one per interface.
        margin_lsb: RID 9 send-period margin in 50 us LSBs for the timeout branch.

    Returns:
        (list[DumpEvaluation]) One evaluation per capture file, ordered by filename.

    Raises:
        FileNotFoundError: If the directory holds no `*.json` capture.
    """
    dump_files = sorted(fixture_dir.glob("*.json"))
    if not dump_files:
        raise FileNotFoundError(f"no *.json RID capture in {fixture_dir}")
    return [evaluate_dump(load_dump(path), margin_lsb) for path in dump_files]
