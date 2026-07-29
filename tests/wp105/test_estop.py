"""The modelled hard-E-Stop terminal state, and the static absence of a recovery-by-read path.

`16` M-2 is the premise: power is cut, CAN dies, so "read state after the stop and recover"
is impossible. The drop is a fact (`12` NFR-SAF-009); its speed is not measured (`16` M-3).

Two unlike checks share this file, and the difference matters. `observe_hard_estop` returns
the premise as constants, so the tests over it pin the model against a silent edit — they
measure nothing, and they are not acceptance ⑨⑩. The physical half of ⑨⑩ is deferred to a
real capture and asserted in `test_deferred_acceptances.test_deferred_hard_estop_drop`. Only
the static scan below is a finding: no function in the package recovers by reading.
"""

from __future__ import annotations

from pathlib import Path

import backend.torque_bringup as torque_bringup
from backend.torque_bringup import (
    find_post_estop_recovery,
    observe_hard_estop,
)


def test_estop_kills_can() -> None:
    # The model says the bus dies with the power (16 M-2). Pinned, not measured — the
    # measurement is the deferred capture's.
    record = observe_hard_estop()
    assert record.can_alive is False


def test_estop_has_no_recovery_by_state_read() -> None:
    # Recovering by reading is impossible by design, so the model may never claim it.
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
    # The model records the drop as a fact and leaves its speed unmeasured (16 M-3, §9-10);
    # a speed appearing here would be a gate the plan removed coming back by accident.
    record = observe_hard_estop()
    assert record.drop_occurred is True
    assert record.drop_speed_measured is False
