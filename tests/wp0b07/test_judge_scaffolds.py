"""The gate judgment scaffolds, unit-tested on synthetic values.

These are the decision functions the three gates apply. The *logic* runs and is
tested here; the *acceptance* — feeding it real read-backs from 16 powered motors —
is deferred to the re-verification hook (see `test_deferred_acceptances.py`). Testing
a pure function on synthetic inputs is not a hardware green; it is proving the
scaffold the deferred run will re-use.
"""

from __future__ import annotations

from backend.can.rid.judge import (
    PgStatus,
    Rid9Branch,
    judge_j7,
    judge_rid9_timeout,
    judge_vmax,
)
from backend.can.rid.layout import ARM_SEND_IDS
from backend.can.rid.motor_limits import MotorType

_MARGIN_LSB = 20


# --- PG-J7-001: RID 23 TMAX -> J7 motor type (03 FR-MOT-004) ---


def test_j7_tmax_10_passes_as_dm4310() -> None:
    judgment = judge_j7(10.0)
    assert judgment.status is PgStatus.PASS
    assert judgment.classified_type is MotorType.DM4310
    assert not judgment.triggers_wp0c03


def test_j7_tmax_5_fails_blocking_and_triggers_wp0c03() -> None:
    judgment = judge_j7(5.0)
    assert judgment.status is PgStatus.FAIL_BLOCKING
    assert judgment.classified_type is MotorType.DM3507
    assert judgment.triggers_wp0c03


def test_j7_unclassifiable_tmax_fails_blocking() -> None:
    judgment = judge_j7(3.3)
    assert judgment.status is PgStatus.FAIL_BLOCKING
    assert judgment.classified_type is None
    assert judgment.triggers_wp0c03


# --- PG-VMAX-001: DM4340 RID 22 VMAX -> 8/10/20 (16 §3.1) ---


def test_vmax_classifies_the_three_variants() -> None:
    assert judge_vmax(8.0).classified_variant == 8.0
    assert judge_vmax(10.0).classified_variant == 10.0
    assert judge_vmax(20.0).classified_variant == 20.0


def test_vmax_always_requires_supply_voltage() -> None:
    assert judge_vmax(8.0).supply_voltage_required


def test_vmax_off_variant_is_unclassified() -> None:
    assert judge_vmax(14.0).classified_variant is None


# --- PG-RID-001: RID 9 timeout branch over all motors (16 M-4, 12 NFR-SAF-007) ---


def _full_arm(value_lsb: int) -> dict[int, int]:
    return dict.fromkeys(ARM_SEND_IDS, value_lsb)


def test_partial_read_fails_blocking() -> None:
    # One motor missing => read failure => torque-ON forbidden (03 FR-MOT-003).
    observed = _full_arm(1000)
    del observed[0x04]
    judgment = judge_rid9_timeout(ARM_SEND_IDS, observed, _MARGIN_LSB)
    assert judgment.status is PgStatus.FAIL_BLOCKING
    assert judgment.missing_motor_ids == (0x04,)


def test_full_read_passes() -> None:
    judgment = judge_rid9_timeout(ARM_SEND_IDS, _full_arm(1000), _MARGIN_LSB)
    assert judgment.status is PgStatus.PASS
    assert judgment.missing_motor_ids == ()
    assert not judgment.heterogeneous


def test_zero_value_selects_hw_fallback_branch() -> None:
    judgment = judge_rid9_timeout(ARM_SEND_IDS, _full_arm(0), _MARGIN_LSB)
    branches = {m.branch for m in judgment.per_motor}
    assert branches == {Rid9Branch.HW_FALLBACK_DISABLED}


def test_value_at_or_under_margin_selects_raise_tx_branch() -> None:
    judgment = judge_rid9_timeout(ARM_SEND_IDS, _full_arm(_MARGIN_LSB), _MARGIN_LSB)
    assert {m.branch for m in judgment.per_motor} == {Rid9Branch.RAISE_TX_OR_NORMALIZE}


def test_heterogeneous_values_are_flagged() -> None:
    observed = _full_arm(1000)
    observed[0x01] = 0
    observed[0x02] = 5
    judgment = judge_rid9_timeout(ARM_SEND_IDS, observed, _MARGIN_LSB)
    assert judgment.heterogeneous
    by_id = {m.motor_id: m for m in judgment.per_motor}
    assert by_id[0x01].branch is Rid9Branch.HW_FALLBACK_DISABLED
    assert by_id[0x02].branch is Rid9Branch.RAISE_TX_OR_NORMALIZE
    assert by_id[0x03].branch is Rid9Branch.ADEQUATE


def test_timeout_microseconds_uses_50us_lsb() -> None:
    judgment = judge_rid9_timeout(ARM_SEND_IDS, _full_arm(1000), _MARGIN_LSB)
    # 1000 LSB * 50 us = 50000 us (16 M-4).
    assert judgment.per_motor[0].microseconds == 50000
