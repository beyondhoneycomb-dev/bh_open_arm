"""Shared fixtures for the WP-2C-04 threshold-mode / confirm-hysteresis acceptance tests.

The accel scenario is a synthetic trapezoidal single-joint move with NO external force. Its residual
is pure inertial-torque leakage r_i = leak_i.|qddot_i| — the M(q).qddot term that bleeds into the
GMO residual when acceleration limits are off (spec 12 §2.13). Every confirmation the gate raises on
this trace is therefore a false positive by construction, which is what makes the accel-term /
TRAJECTORY_SCHEDULED false-positive measurement (acceptance ②) honest rather than staged: the leak
coefficient is the ground truth, and a correctly tuned accel term must cancel it.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from backend.threshold import ThresholdConfig

# The joint driven in the accel scenario (joint1, thr0 = 4.0 Nm).
DRIVEN_JOINT = 0

# Synthetic effective-inertia leak coefficient [Nm.s^2/rad]: the fraction of M_ii that reaches the
# residual. Set equal to the accel coefficient a_i a tuned config uses, so a matched accel term
# cancels it exactly. Kept at ACC_COEFF_MAX (0.5) so the whole scenario stays inside the spec range.
LEAK_COEFF = 0.5

# Commanded acceleration on the driven joint [rad/s^2]. Unbounded here on purpose — that is the
# v2.0 reality (has_acceleration_limits: false). Chosen so leak = LEAK_COEFF x ACCEL = 10 Nm sits
# well above the 4.0 Nm STATIC threshold, forcing a STATIC false positive.
ACCEL_MAG = 20.0

DT = 0.001
N_ACCEL = 15
N_CRUISE = 20
N_DECEL = 15

# A small constant model offset on every joint [Nm]. Below every joint's release level
# (0.7 x 0.7 = 0.49 Nm on the weakest joint), so it never confirms — it only proves the gate
# ignores sub-threshold baseline residual.
BASELINE_RESIDUAL = 0.05

_N_JOINTS = 7


@dataclass(frozen=True)
class AccelScenario:
    """One synthetic collision-free trapezoidal move and the residual it induces.

    Attributes:
        qdot: Per-step joint velocity [rad/s], one 7-tuple per step.
        qddot: Per-step joint acceleration [rad/s^2], one 7-tuple per step.
        residual: Per-step GMO residual [Nm] with no external force — inertial leak plus baseline.
        driven_joint: The joint index that moves.
        leak_coeff: The leak coefficient used to build the residual [Nm.s^2/rad].
    """

    qdot: tuple[tuple[float, ...], ...]
    qddot: tuple[tuple[float, ...], ...]
    residual: tuple[tuple[float, ...], ...]
    driven_joint: int
    leak_coeff: float


def _row(joint: int, value: float) -> tuple[float, ...]:
    """A 7-wide row that is `value` at `joint` and 0.0 elsewhere."""
    return tuple(value if index == joint else 0.0 for index in range(_N_JOINTS))


def build_accel_scenario() -> AccelScenario:
    """Build the trapezoidal accel/cruise/decel scenario and its collision-free residual."""
    qdot_rows: list[tuple[float, ...]] = []
    qddot_rows: list[tuple[float, ...]] = []
    residual_rows: list[tuple[float, ...]] = []

    peak_velocity = ACCEL_MAG * N_ACCEL * DT
    for step in range(N_ACCEL + N_CRUISE + N_DECEL):
        if step < N_ACCEL:
            accel = ACCEL_MAG
            velocity = ACCEL_MAG * step * DT
        elif step < N_ACCEL + N_CRUISE:
            accel = 0.0
            velocity = peak_velocity
        else:
            accel = -ACCEL_MAG
            elapsed = step - (N_ACCEL + N_CRUISE)
            velocity = peak_velocity - ACCEL_MAG * elapsed * DT

        qdot_rows.append(_row(DRIVEN_JOINT, velocity))
        qddot_rows.append(_row(DRIVEN_JOINT, accel))

        leak = LEAK_COEFF * abs(accel)
        residual_rows.append(
            tuple(
                BASELINE_RESIDUAL + (leak if index == DRIVEN_JOINT else 0.0)
                for index in range(_N_JOINTS)
            )
        )

    return AccelScenario(
        qdot=tuple(qdot_rows),
        qddot=tuple(qddot_rows),
        residual=tuple(residual_rows),
        driven_joint=DRIVEN_JOINT,
        leak_coeff=LEAK_COEFF,
    )


@pytest.fixture
def default_config() -> ThresholdConfig:
    """The spec 12 §2.12 [A] default threshold configuration."""
    return ThresholdConfig.default()


@pytest.fixture
def accel_scenario() -> AccelScenario:
    """The synthetic collision-free trapezoidal accel scenario."""
    return build_accel_scenario()
