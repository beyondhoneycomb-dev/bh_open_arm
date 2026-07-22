"""WP-2C-01 acceptance ②: detection activation is refused without measured torque.

The momentum observer's balance carries `tau_meas`, present only when `use_velocity_and_torque` is
true. This band's default is off (spec §3.0): until PG-FRIC-001 establishes friction the observer
stays disabled even when it is the selected method. These tests exercise the gate that composes the
reused WP-1-06 preconditions (accel limit, friction-established) with the torque-feedback bar
WP-2C-01 adds — and confirm the selector enum is reused, not redefined.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.gmo import (
    DetectionMethod,
    ResidualDetectionRefusedError,
    TorqueFeedbackAbsentError,
    assert_torque_feedback_available,
    observer_detection_active,
)
from backend.gmo.selector import DEFAULT_DETECTION_METHOD
from backend.safety_bringup.detection import DetectionMethod as SafetyDetectionMethod


def _friction_file(tmp_path: Path, *, established: bool) -> Path:
    """Write a friction descriptor that is present-and-non-empty, or empty (not established).

    The two states get distinct filenames so a test can hold both at once without one write
    clobbering the other.
    """
    path = tmp_path / ("friction_established.yaml" if established else "friction_empty.yaml")
    path.write_text("joint1: {f_o: 0.0}\n" if established else "")
    return path


def test_torque_feedback_absent_refuses_activation(tmp_path: Path) -> None:
    """`use_velocity_and_torque=false` refuses observer activation — tau_meas absent (②)."""
    friction = _friction_file(tmp_path, established=True)
    with pytest.raises(TorqueFeedbackAbsentError):
        observer_detection_active(
            DetectionMethod.MOMENTUM_OBSERVER,
            use_velocity_and_torque=False,
            accel_limit_active=True,
            friction_yaml_path=friction,
        )


def test_bare_torque_feedback_assertion_refuses(tmp_path: Path) -> None:
    """The torque-feedback bar refuses on its own, independent of the other gates (②)."""
    with pytest.raises(TorqueFeedbackAbsentError):
        assert_torque_feedback_available(False)
    assert_torque_feedback_available(True)


def test_accel_limit_off_refuses_residual_method(tmp_path: Path) -> None:
    """A residual method with the accel limit off is refused — the reused WP-1-06 precondition."""
    friction = _friction_file(tmp_path, established=True)
    with pytest.raises(ResidualDetectionRefusedError):
        observer_detection_active(
            DetectionMethod.MOMENTUM_OBSERVER,
            use_velocity_and_torque=True,
            accel_limit_active=False,
            friction_yaml_path=friction,
        )


def test_active_only_when_friction_established(tmp_path: Path) -> None:
    """With torque and accel limit satisfied, activity follows the friction-established gate."""
    established = _friction_file(tmp_path, established=True)
    not_established = _friction_file(tmp_path, established=False)
    assert observer_detection_active(DetectionMethod.MOMENTUM_OBSERVER, True, True, established)
    assert not observer_detection_active(
        DetectionMethod.MOMENTUM_OBSERVER, True, True, not_established
    )


def test_default_off_when_friction_absent(tmp_path: Path) -> None:
    """This band's default is off: an absent friction file leaves detection inactive (§3.0)."""
    absent = tmp_path / "does_not_exist.yaml"
    assert not observer_detection_active(DetectionMethod.MOMENTUM_OBSERVER, True, True, absent)


def test_non_residual_methods_do_not_activate_the_observer(tmp_path: Path) -> None:
    """DISABLED and CURRENT_LIMIT are not the observer, so it reports inactive without raising."""
    friction = _friction_file(tmp_path, established=True)
    assert not observer_detection_active(DetectionMethod.DISABLED, True, True, friction)
    assert not observer_detection_active(DetectionMethod.CURRENT_LIMIT, True, True, friction)


def test_selector_enum_is_the_reused_one() -> None:
    """The detection-method enum is WP-1-06's, re-exported, not a second definition."""
    assert DetectionMethod is SafetyDetectionMethod
    assert DEFAULT_DETECTION_METHOD is DetectionMethod.MOMENTUM_OBSERVER
    assert {method.value for method in DetectionMethod} == {
        "MOMENTUM_OBSERVER",
        "TORQUE_RESIDUAL",
        "CURRENT_LIMIT",
        "DISABLED",
    }
