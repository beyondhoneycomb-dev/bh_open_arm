"""Acceptance ⑤⑦⑧⑫: hold maintenance, lease expiry, one-frame stop, SAFE_HOLD != torque-0.

These drive the actuation spine offline (fake CAN writer, manual clock). The lease-expiry-
forces-a-hold logic is the spine's; this proves it holds under a WP-1-05 present-pose hold
and measures the properties the acceptance gates name. The physical joint drift is deferred.
"""

from __future__ import annotations

import dataclasses

import pytest

from backend.actuation import MIT_BATCH_WIDTH, positions_to_batch
from backend.torque_bringup import (
    SafeHoldViolationError,
    assert_safe_hold,
    verify_hold_maintenance,
    verify_lease_expiry,
)
from contracts.units import Rad


@pytest.fixture
def present_pose() -> tuple[Rad, ...]:
    return tuple(Rad(0.05 * index) for index in range(MIT_BATCH_WIDTH))


def test_hold_maintenance_holds_every_tick(present_pose: tuple[Rad, ...]) -> None:
    # Acceptance ⑤: no producer, deadman renewed => every tick is a hold, no drift.
    report = verify_hold_maintenance(present_pose, ticks=500)
    assert report.all_holds
    assert report.commanded_drift_rad == 0.0


def test_hold_stop_path_is_exactly_one_frame_per_tick(present_pose: tuple[Rad, ...]) -> None:
    # Acceptance ⑧: the Cat-2 hold is one MIT frame per tick — no zero, no double.
    report = verify_hold_maintenance(present_pose, ticks=500)
    assert report.frames_written == report.ticks


def test_hold_send_period_under_rid9_margin(present_pose: tuple[Rad, ...]) -> None:
    # Acceptance ②: the hold refresh interval stays under the RID-9 no-send margin.
    report = verify_hold_maintenance(present_pose, ticks=500)
    assert report.send_period_under_margin
    assert report.max_send_interval_sec < report.rid9_no_send_margin_sec


def test_lease_expiry_emits_hold_on_the_lapse_tick(present_pose: tuple[Rad, ...]) -> None:
    # Acceptance ⑦: renewal stops => the very tick the lease lapses emits the hold.
    report = verify_lease_expiry(present_pose, warmup_ticks=20, coast_ticks=400)
    assert report.first_expiry_condition_tick >= 0
    assert report.first_hold_tick == report.first_expiry_condition_tick
    assert report.delay_ticks == 0
    assert report.holds_after_expiry


def test_safe_hold_accepts_gravity_comp_hold(present_pose: tuple[Rad, ...]) -> None:
    # A present-pose hold from the spine has kp>0 and passes the SAFE_HOLD check.
    assert_safe_hold(positions_to_batch(present_pose))


def test_safe_hold_rejects_torque_zero_frame(present_pose: tuple[Rad, ...]) -> None:
    # Acceptance ⑫: a zero-stiffness frame is a torque-0 drop, not a SAFE_HOLD.
    limp = tuple(
        dataclasses.replace(command, kp=0.0) for command in positions_to_batch(present_pose)
    )
    with pytest.raises(SafeHoldViolationError, match="drops a brakeless arm"):
        assert_safe_hold(limp)


def test_safe_hold_rejects_negative_stiffness(present_pose: tuple[Rad, ...]) -> None:
    negative = tuple(
        dataclasses.replace(command, kp=-1.0) for command in positions_to_batch(present_pose)
    )
    with pytest.raises(SafeHoldViolationError):
        assert_safe_hold(negative)
