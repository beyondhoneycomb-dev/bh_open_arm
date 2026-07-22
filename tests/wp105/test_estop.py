"""Acceptance ⑨⑩: the hard E-Stop kills CAN, drops the arm, and has no recovery-by-read.

`16` M-2 is the premise: power is cut, CAN dies, "read state after stop and recover" is
impossible. The drop is a fact (`12` NFR-SAF-009); its speed is not measured (`16` M-3). The
absence of a recovery path is checked statically over the package.
"""

from __future__ import annotations

from pathlib import Path

import backend.torque_bringup as torque_bringup
from backend.torque_bringup import (
    find_post_estop_recovery,
    observe_hard_estop,
)


def test_estop_kills_can() -> None:
    # Acceptance ⑨: an E-Stop cuts power, so the CAN bus dies with it (16 M-2).
    record = observe_hard_estop()
    assert record.can_alive is False


def test_estop_has_no_recovery_by_state_read() -> None:
    # Acceptance ⑨: reading state to recover is impossible by design — the bus is dead.
    assert observe_hard_estop().recovery_by_state_read is False


def test_no_post_estop_recovery_path_in_package() -> None:
    # Acceptance ⑨: the machine proof — no function recovers by reading after a stop.
    package_dir = Path(torque_bringup.__file__).resolve().parent
    assert find_post_estop_recovery(package_dir) == []


def test_recovery_scan_would_catch_a_planted_path(tmp_path: Path) -> None:
    # The static-absence check is real: a planted recovery def is flagged, proving the
    # empty result above is a finding of absence, not a scanner that never fires.
    (tmp_path / "leak.py").write_text(
        "def resume_after_estop():\n    return read_state()\n", encoding="utf-8"
    )
    found = find_post_estop_recovery(tmp_path)
    assert found and "resume_after_estop" in found[0]


def test_drop_recorded_but_speed_not_measured() -> None:
    # Acceptance ⑩: the drop is recorded as a fact; its speed is not measured (16 M-3).
    record = observe_hard_estop()
    assert record.drop_occurred is True
    assert record.drop_speed_measured is False
