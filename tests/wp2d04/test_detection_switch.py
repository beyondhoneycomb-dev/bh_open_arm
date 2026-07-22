"""Acceptance ① and ② — the residual trip is switched off, the fault trips stay on.

A hand-guide force is an external residual, so Freedrive suppresses the residual trip and a
push does not false-detect (①). Every hardware fault — ERR nibble, over-temperature, comm
loss — and a limit violation still trip during Freedrive (②). Switching a retained detector
off is the "detection fully off" FAIL_BLOCKING branch.
"""

from __future__ import annotations

import pytest

pytest.importorskip("mujoco")

from backend.freedrive_walls import (
    HARDWARE_FAULT_DETECTORS,
    DetectionRetainedError,
    DetectorKind,
    FreedriveResidualPolicy,
    assert_freedrive_detection_retained,
)
from backend.temp_gripper import DRIVE_TEMP_FAULT_CAP_C, MotorThermal
from tests.wp2d04._fixtures import (
    SYNTHETIC_UPPER_RAD,
    fault_status_byte,
    freedrive_suite,
    healthy_status_byte,
    ok_thermals,
)

_HUGE_RESIDUAL = [999.0] * 7
_QUIET = [0.0] * 7


def _healthy_recv() -> list[int]:
    return [healthy_status_byte()]


def test_human_push_does_not_false_detect() -> None:
    """A large residual with healthy hardware and an in-limit pose trips nothing (①)."""
    _, _, suite = freedrive_suite()
    verdict = suite.evaluate(_HUGE_RESIDUAL, _QUIET, _healthy_recv, ok_thermals())
    assert not verdict.tripped
    assert verdict.residual.suppressed
    assert verdict.tripped_kinds == ()


def test_err_nibble_trips_during_freedrive() -> None:
    """A motor ERR-nibble fault trips even while the residual is suppressed (②)."""
    _, _, suite = freedrive_suite()
    verdict = suite.evaluate(_QUIET, _QUIET, lambda: [fault_status_byte()], ok_thermals())
    assert verdict.tripped
    assert DetectorKind.MOTOR_FAULT in verdict.tripped_kinds


def test_comm_loss_trips_during_freedrive() -> None:
    """Silence past the timeout trips comm loss even in Freedrive (②)."""
    _, clock, suite = freedrive_suite()
    clock.advance(1.0)  # well past the comm-loss timeout
    verdict = suite.evaluate(_QUIET, _QUIET, list, ok_thermals())
    assert verdict.tripped
    assert DetectorKind.COMM_LOSS in verdict.tripped_kinds


def test_over_temperature_trips_during_freedrive() -> None:
    """A driver channel over its fault cap trips temperature even in Freedrive (②)."""
    _, _, suite = freedrive_suite()
    hot = (MotorThermal(drive_c=DRIVE_TEMP_FAULT_CAP_C + 5.0, coil_c=30.0), *ok_thermals()[1:])
    verdict = suite.evaluate(_QUIET, _QUIET, _healthy_recv, hot)
    assert verdict.tripped
    assert DetectorKind.TEMPERATURE in verdict.tripped_kinds


def test_limit_violation_trips_during_freedrive() -> None:
    """A joint driven past its soft limit trips the limit detector even in Freedrive (②)."""
    _, _, suite = freedrive_suite()
    q = [0.0] * 7
    q[2] = SYNTHETIC_UPPER_RAD[2] + 0.5
    verdict = suite.evaluate(_HUGE_RESIDUAL, q, _healthy_recv, ok_thermals())
    assert verdict.tripped
    assert DetectorKind.LIMIT_VIOLATION in verdict.tripped_kinds
    assert verdict.limit_flagged == (2,)


def test_separate_threshold_residual_can_still_trip() -> None:
    """Under a separate threshold set a genuine over-threshold residual still trips."""
    policy = FreedriveResidualPolicy(freedrive_thresholds=[50.0] * 7)
    _, _, suite = freedrive_suite(residual_policy=policy)
    verdict = suite.evaluate(_HUGE_RESIDUAL, _QUIET, _healthy_recv, ok_thermals())
    assert not verdict.residual.suppressed
    assert verdict.residual.tripped
    assert DetectorKind.RESIDUAL in verdict.tripped_kinds


def test_disabling_a_hardware_fault_is_fail_blocking() -> None:
    """Switching off any hardware-fault detector is refused (detection fully off)."""
    for kind in HARDWARE_FAULT_DETECTORS:
        with pytest.raises(DetectionRetainedError):
            assert_freedrive_detection_retained({kind: False})


def test_disabling_limit_violation_is_fail_blocking() -> None:
    """Switching off limit-violation detection is refused (FR-MAN-037 keeps it on)."""
    with pytest.raises(DetectionRetainedError):
        assert_freedrive_detection_retained({DetectorKind.LIMIT_VIOLATION: False})


def test_suppressing_only_the_residual_is_allowed() -> None:
    """Freedrive may suppress the residual with every retained detector still on."""
    assert_freedrive_detection_retained({DetectorKind.RESIDUAL: False})
