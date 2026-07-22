"""Threshold-mode evaluation: STATIC / VELOCITY_SCALED / TRAJECTORY_SCHEDULED and the accel term.

The per-joint detection threshold is a function of joint state, chosen to hold the residual margin
roughly constant across the motion so a fixed collision force trips detection whether the arm is
still or moving fast (FR-SAF-021, spec 12 §2.5/§2.13):

* `STATIC`          thr_i = thr0_i
* `VELOCITY_SCALED` thr_i = thr0_i + c_i.|qdot_i|                       (live measured velocity)
* `TRAJECTORY_SCHEDULED` thr_i = the pre-computed profile value at the current trajectory step

The optional acceleration term `+ a_i.|qddot_i|` is the dominant false-positive control: with
acceleration limits off, the inertial torque M(q).qddot leaks into the residual (spec 12 §2.13),
so raising the threshold in proportion to |qddot| absorbs the leak. It is applied on top of STATIC
and VELOCITY_SCALED from the *live* qddot; TRAJECTORY_SCHEDULED bakes the same term into its
profile from the *planned* qddot instead of adding it live, so it is elevated across the whole
accel region rather than lagging behind a differentiated velocity estimate — which is exactly why
a scheduled profile suppresses accel-onset false positives a live term can still miss.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from backend.threshold.calibration import ThresholdCalibration
from backend.threshold.constants import (
    ACC_COEFF_DEFAULT,
    ACC_COEFF_MAX,
    ACC_COEFF_MIN,
    CONFIRM_SAMPLES_DEFAULT,
    CONFIRM_SAMPLES_MAX,
    CONFIRM_SAMPLES_MIN,
    HYSTERESIS_RATIO_DEFAULT,
    HYSTERESIS_RATIO_MAX,
    HYSTERESIS_RATIO_MIN,
    N_ARM_JOINTS,
    VEL_COEFF_DEFAULT,
    VEL_COEFF_MAX,
    VEL_COEFF_MIN,
)
from backend.threshold.errors import ThresholdConfigError


class ThresholdMode(Enum):
    """The three time-varying threshold schedules a caller may select (FR-SAF-021)."""

    STATIC = "STATIC"
    VELOCITY_SCALED = "VELOCITY_SCALED"
    TRAJECTORY_SCHEDULED = "TRAJECTORY_SCHEDULED"


def _check_width(name: str, values: Sequence[float] | Sequence[bool]) -> None:
    """Raise `ThresholdConfigError` unless `values` is exactly `N_ARM_JOINTS` wide."""
    if len(values) != N_ARM_JOINTS:
        raise ThresholdConfigError(f"{name} must be {N_ARM_JOINTS} joints wide, got {len(values)}")


def _check_range(name: str, values: Sequence[float], low: float, high: float) -> None:
    """Raise `ThresholdConfigError` if any element of `values` falls outside [low, high]."""
    for joint, value in enumerate(values):
        if not low <= float(value) <= high:
            raise ThresholdConfigError(f"{name}[{joint}] = {value} is outside [{low}, {high}]")


@dataclass(frozen=True)
class ThresholdConfig:
    """A frozen, validated collision-detection threshold configuration (spec 12 §2.12 [A]).

    Attributes:
        calibration: The consumed WP-2C-03 base threshold thr0.
        mode: Which schedule maps joint state to the per-joint threshold.
        vel_coeff: Per-joint velocity coefficient c_i [Nm.s/rad], each in [0, 1.0].
        acc_coeff: Per-joint acceleration coefficient a_i [Nm.s^2/rad], each in [0, 0.5].
        use_accel_term: Whether the acceleration term participates. When false, `acc_coeff` is
            inert — a caller can keep a tuned vector and toggle the term without losing it.
        confirm_samples: Consecutive over-threshold samples required to confirm, in [1, 50].
        hysteresis_ratio: Release-threshold ratio, in [0.3, 0.95].
        per_joint_enable: Per-joint detection enable; a disabled joint never confirms.
    """

    calibration: ThresholdCalibration
    mode: ThresholdMode
    vel_coeff: tuple[float, ...]
    acc_coeff: tuple[float, ...]
    use_accel_term: bool
    confirm_samples: int
    hysteresis_ratio: float
    per_joint_enable: tuple[bool, ...]

    def __post_init__(self) -> None:
        """Validate every per-joint width, coefficient range, and scalar bound.

        Raises:
            ThresholdConfigError: On any wrong-width array or out-of-range value.
        """
        _check_width("vel_coeff", self.vel_coeff)
        _check_width("acc_coeff", self.acc_coeff)
        _check_width("per_joint_enable", self.per_joint_enable)
        _check_range("vel_coeff", self.vel_coeff, VEL_COEFF_MIN, VEL_COEFF_MAX)
        _check_range("acc_coeff", self.acc_coeff, ACC_COEFF_MIN, ACC_COEFF_MAX)
        if not CONFIRM_SAMPLES_MIN <= self.confirm_samples <= CONFIRM_SAMPLES_MAX:
            raise ThresholdConfigError(
                f"confirm_samples {self.confirm_samples} is outside "
                f"[{CONFIRM_SAMPLES_MIN}, {CONFIRM_SAMPLES_MAX}]"
            )
        if not HYSTERESIS_RATIO_MIN <= self.hysteresis_ratio <= HYSTERESIS_RATIO_MAX:
            raise ThresholdConfigError(
                f"hysteresis_ratio {self.hysteresis_ratio} is outside "
                f"[{HYSTERESIS_RATIO_MIN}, {HYSTERESIS_RATIO_MAX}]"
            )

    @classmethod
    def default(cls, calibration: ThresholdCalibration | None = None) -> ThresholdConfig:
        """Return the spec 12 §2.12 [A] default configuration.

        VELOCITY_SCALED, c_i = 0.05, a_i = 0.0 with the accel term off, confirm_samples = 5,
        hysteresis_ratio = 0.7, all joints enabled.

        Args:
            calibration: Base threshold to use; the literature default when omitted.

        Returns:
            (ThresholdConfig) The default configuration.
        """
        base = calibration if calibration is not None else ThresholdCalibration.literature_default()
        return cls(
            calibration=base,
            mode=ThresholdMode.VELOCITY_SCALED,
            vel_coeff=(VEL_COEFF_DEFAULT,) * N_ARM_JOINTS,
            acc_coeff=(ACC_COEFF_DEFAULT,) * N_ARM_JOINTS,
            use_accel_term=False,
            confirm_samples=CONFIRM_SAMPLES_DEFAULT,
            hysteresis_ratio=HYSTERESIS_RATIO_DEFAULT,
            per_joint_enable=(True,) * N_ARM_JOINTS,
        )


@dataclass(frozen=True)
class ThresholdSchedule:
    """A pre-computed per-step threshold profile for TRAJECTORY_SCHEDULED mode.

    Attributes:
        samples: One per-joint threshold vector [Nm] per planned trajectory step, in order.
    """

    samples: tuple[tuple[float, ...], ...]

    def at(self, step: int) -> tuple[float, ...]:
        """Return the scheduled per-joint threshold at a trajectory step.

        A step past the end clamps to the last sample: a controller that overruns the planned
        horizon holds the final elevated profile rather than falling back to a bare STATIC vector.

        Args:
            step: Zero-based trajectory step index.

        Returns:
            (tuple[float, ...]) The per-joint threshold [Nm] for that step.

        Raises:
            ThresholdConfigError: If the schedule is empty or `step` is negative.
        """
        if not self.samples:
            raise ThresholdConfigError("threshold schedule is empty")
        if step < 0:
            raise ThresholdConfigError(f"schedule step {step} is negative")
        index = min(step, len(self.samples) - 1)
        return self.samples[index]


def build_schedule(
    config: ThresholdConfig,
    planned_qdot: Sequence[Sequence[float]],
    planned_qddot: Sequence[Sequence[float]],
) -> ThresholdSchedule:
    """Pre-compute the TRAJECTORY_SCHEDULED threshold profile from a planned trajectory.

    Each step's threshold is thr0_i + c_i.|qdot_planned_i| plus, when the accel term is on,
    a_i.|qddot_planned_i|. Because the profile reads the *planned* acceleration, the accel region is
    elevated across its full span, not lagging a live velocity derivative (spec 12 §2.13, option ③).

    Args:
        config: The threshold configuration supplying thr0 and the coefficients.
        planned_qdot: Planned joint velocity [rad/s] per step, each row `N_ARM_JOINTS` wide.
        planned_qddot: Planned joint acceleration [rad/s^2] per step, same shape as `planned_qdot`.

    Returns:
        (ThresholdSchedule) The per-step threshold profile.

    Raises:
        ThresholdConfigError: If the two trajectories differ in length, or a row is the wrong width.
    """
    if len(planned_qdot) != len(planned_qddot):
        raise ThresholdConfigError(
            f"planned_qdot has {len(planned_qdot)} steps but planned_qddot has {len(planned_qddot)}"
        )
    thr0 = config.calibration.thr0
    samples: list[tuple[float, ...]] = []
    for qdot_row, qddot_row in zip(planned_qdot, planned_qddot, strict=True):
        _check_width("planned_qdot row", qdot_row)
        _check_width("planned_qddot row", qddot_row)
        row = tuple(
            thr0[joint]
            + config.vel_coeff[joint] * abs(qdot_row[joint])
            + (config.acc_coeff[joint] * abs(qddot_row[joint]) if config.use_accel_term else 0.0)
            for joint in range(N_ARM_JOINTS)
        )
        samples.append(row)
    return ThresholdSchedule(samples=tuple(samples))


def effective_thresholds(
    config: ThresholdConfig,
    qdot: Sequence[float],
    qddot: Sequence[float],
    scheduled: Sequence[float] | None = None,
) -> tuple[float, ...]:
    """Return the per-joint detection threshold [Nm] for one sample under the configured mode.

    STATIC uses thr0; VELOCITY_SCALED adds c_i.|qdot_i| from the live velocity; TRAJECTORY_SCHEDULED
    returns the pre-computed `scheduled` vector (already carrying its own vel/accel terms). The
    optional accel term a_i.|qddot_i| is added live for STATIC and VELOCITY_SCALED only — for
    TRAJECTORY_SCHEDULED it is already inside the profile, so adding it again would double-count.

    Args:
        config: The threshold configuration.
        qdot: Live joint velocity [rad/s], `N_ARM_JOINTS` wide.
        qddot: Live joint acceleration [rad/s^2], `N_ARM_JOINTS` wide.
        scheduled: The `ThresholdSchedule.at(step)` vector; required in TRAJECTORY_SCHEDULED mode.

    Returns:
        (tuple[float, ...]) The per-joint threshold [Nm] for this sample.

    Raises:
        ThresholdConfigError: On a wrong-width input, or a missing schedule in TRAJECTORY_SCHEDULED.
    """
    _check_width("qdot", qdot)
    _check_width("qddot", qddot)
    thr0 = config.calibration.thr0

    if config.mode is ThresholdMode.TRAJECTORY_SCHEDULED:
        if scheduled is None:
            raise ThresholdConfigError(
                "TRAJECTORY_SCHEDULED requires a scheduled threshold vector for this step"
            )
        _check_width("scheduled", scheduled)
        return tuple(float(value) for value in scheduled)

    live_accel = config.use_accel_term
    result: list[float] = []
    for joint in range(N_ARM_JOINTS):
        threshold = thr0[joint]
        if config.mode is ThresholdMode.VELOCITY_SCALED:
            threshold += config.vel_coeff[joint] * abs(qdot[joint])
        if live_accel:
            threshold += config.acc_coeff[joint] * abs(qddot[joint])
        result.append(threshold)
    return tuple(result)
