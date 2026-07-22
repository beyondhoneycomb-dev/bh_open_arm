"""Acceptance ② — accel term / TRAJECTORY_SCHEDULED reduce accel-region false positives (measured).

The scenario (`conftest.build_accel_scenario`) is a collision-free trapezoidal move whose residual
is pure inertial leakage leak.|qddot| — the M(q).qddot term that pollutes the residual when accel
limits are off (spec 12 §2.13). Any confirmation is therefore a false positive by construction. The
test runs the same trace through four configurations and counts confirmations:

* STATIC and VELOCITY_SCALED (velocity scaling alone) both fire — velocity scaling cannot cover an
  acceleration-driven bump, least of all at accel onset where |qdot| is still small;
* VELOCITY_SCALED with a matched accel term, and TRAJECTORY_SCHEDULED built from the plan, both fire
  zero — the a.|qddot| term raises the threshold exactly where the leak raises the residual.

The counts are the measurement acceptance ② asks for.
"""

from __future__ import annotations

from backend.threshold import (
    ConfirmHysteresisGate,
    ThresholdCalibration,
    ThresholdConfig,
    ThresholdMode,
    build_schedule,
    effective_thresholds,
)
from tests.wp2c04.conftest import AccelScenario

_THR0 = ThresholdCalibration.literature_default().thr0


def _config(mode: ThresholdMode, *, leak_coeff: float, use_accel_term: bool) -> ThresholdConfig:
    """A config whose accel coefficient matches the scenario leak, so a tuned term cancels it."""
    return ThresholdConfig(
        calibration=ThresholdCalibration.literature_default(),
        mode=mode,
        vel_coeff=(0.05,) * 7,
        acc_coeff=(leak_coeff,) * 7,
        use_accel_term=use_accel_term,
        confirm_samples=5,
        hysteresis_ratio=0.7,
        per_joint_enable=(True,) * 7,
    )


def _count_false_positives(config: ThresholdConfig, scenario: AccelScenario) -> int:
    """Run the gate over the scenario and count confirmation events (all false positives here)."""
    gate = ConfirmHysteresisGate(config)
    schedule = None
    if config.mode is ThresholdMode.TRAJECTORY_SCHEDULED:
        schedule = build_schedule(config, scenario.qdot, scenario.qddot)

    confirmations = 0
    for step in range(len(scenario.residual)):
        scheduled = schedule.at(step) if schedule is not None else None
        thresholds = effective_thresholds(
            config, scenario.qdot[step], scenario.qddot[step], scheduled=scheduled
        )
        update = gate.update(scenario.residual[step], thresholds)
        confirmations += len(update.newly_confirmed)
    return confirmations


def test_scenario_actually_stresses_the_static_threshold(accel_scenario: AccelScenario) -> None:
    """Sanity: the collision-free residual really does exceed the STATIC threshold under accel."""
    joint = accel_scenario.driven_joint
    peak_residual = max(row[joint] for row in accel_scenario.residual)
    assert peak_residual > _THR0[joint]


def test_static_mode_produces_false_positives(accel_scenario: AccelScenario) -> None:
    """STATIC fires on the inertial leak — the false positives the accel term exists to remove."""
    static = _config(
        ThresholdMode.STATIC, leak_coeff=accel_scenario.leak_coeff, use_accel_term=False
    )
    assert _count_false_positives(static, accel_scenario) > 0


def test_velocity_scaling_alone_does_not_fix_it(accel_scenario: AccelScenario) -> None:
    """Velocity scaling without the accel term still fires — |qdot| is low where |qddot| is high."""
    velocity_only = _config(
        ThresholdMode.VELOCITY_SCALED, leak_coeff=accel_scenario.leak_coeff, use_accel_term=False
    )
    assert _count_false_positives(velocity_only, accel_scenario) > 0


def test_accel_term_reduces_false_positives_to_zero(accel_scenario: AccelScenario) -> None:
    """A matched accel term drives the accel-region false-positive count below STATIC, to zero."""
    static = _config(
        ThresholdMode.STATIC, leak_coeff=accel_scenario.leak_coeff, use_accel_term=False
    )
    with_accel = _config(
        ThresholdMode.VELOCITY_SCALED, leak_coeff=accel_scenario.leak_coeff, use_accel_term=True
    )
    static_fp = _count_false_positives(static, accel_scenario)
    accel_fp = _count_false_positives(with_accel, accel_scenario)

    assert accel_fp < static_fp
    assert accel_fp == 0


def test_trajectory_scheduled_suppresses_false_positives(accel_scenario: AccelScenario) -> None:
    """TRAJECTORY_SCHEDULED, built from the plan's |qddot|, also drives false positives to zero."""
    static = _config(
        ThresholdMode.STATIC, leak_coeff=accel_scenario.leak_coeff, use_accel_term=False
    )
    scheduled = _config(
        ThresholdMode.TRAJECTORY_SCHEDULED,
        leak_coeff=accel_scenario.leak_coeff,
        use_accel_term=True,
    )
    static_fp = _count_false_positives(static, accel_scenario)
    scheduled_fp = _count_false_positives(scheduled, accel_scenario)

    assert scheduled_fp < static_fp
    assert scheduled_fp == 0
