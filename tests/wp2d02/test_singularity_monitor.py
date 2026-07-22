"""Acceptance ② and ③ — Cartesian velocity auto-damps below a settable threshold.

The guard turns the smallest singular value into a jog velocity scale on a two-threshold
ramp: full above the warn value, damped between warn and floor, held below the floor.
② is shown two ways: the ramp itself, and end-to-end through the jog — a jog carrying the
guard moves the EE less per step near a singularity than a full-speed jog. ③ is shown by
changing the threshold and watching the same configuration cross from clear to damped.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("mujoco")
pytest.importorskip("mink")
pytest.importorskip("lerobot")

from backend.cartesian_jog import (
    JogAxis,
    JogCommand,
    JogKind,
    JogStopReason,
    build_cartesian_jog,
)
from backend.cartesian_jog.constants import FULL_VELOCITY_SCALE
from backend.singularity import build_singularity_guard
from backend.singularity.constants import DAMPED_FLOOR_SCALE


def _near_singular_state(elbow: float) -> np.ndarray:
    """A 16-value driver state: right elbow toward straight, left arm at home."""
    state = np.zeros(16)
    state[3] = elbow
    state[11] = np.pi / 2
    return state


def _z_jog() -> JogCommand:
    return JogCommand(side="right", kind=JogKind.TRANSLATION, axis=JogAxis.Z, sign=1)


# joint4 values chosen against the model's observed range: 0.3 sits in the damping band
# (sigma_min ~0.027), 0.05 sits below the floor (sigma_min ~0.002).
_DAMPING_ELBOW = 0.3
_CRITICAL_ELBOW = 0.05


def test_ramp_is_full_then_damped_then_critical() -> None:
    jog = build_cartesian_jog()
    guard = build_singularity_guard(jog)

    clear = guard.evaluate("right", jog.arm_joints("right"))  # home, well-conditioned
    assert not clear.damping and clear.velocity_scale == FULL_VELOCITY_SCALE

    damped = guard.evaluate("right", _near_singular_state(_DAMPING_ELBOW)[:7])
    assert damped.damping and not damped.critical
    assert DAMPED_FLOOR_SCALE < damped.velocity_scale < FULL_VELOCITY_SCALE

    critical = guard.evaluate("right", _near_singular_state(_CRITICAL_ELBOW)[:7])
    assert critical.critical and critical.velocity_scale == DAMPED_FLOOR_SCALE


def test_threshold_is_settable_and_moves_the_damping_boundary() -> None:
    # Acceptance ③: the same home configuration is clear under a low threshold and
    # damped under a high one, purely by moving the settable warn threshold.
    jog = build_cartesian_jog()
    guard = build_singularity_guard(jog, warn_sigma_min=0.05, floor_sigma_min=0.01)
    home = jog.arm_joints("right")

    assert not guard.evaluate("right", home).damping
    guard.set_warn_sigma_min(0.2)
    assert guard.evaluate("right", home).damping
    guard.set_warn_sigma_min(0.05)
    assert not guard.evaluate("right", home).damping


def test_threshold_validation_rejects_inverted_or_nonpositive() -> None:
    jog = build_cartesian_jog()
    guard = build_singularity_guard(jog)
    with pytest.raises(ValueError):
        guard.set_floor_sigma_min(0.0)
    with pytest.raises(ValueError):
        guard.set_warn_sigma_min(guard.floor_sigma_min / 2.0)


def test_jog_carrying_the_guard_damps_ee_motion_near_a_singularity() -> None:
    # End-to-end ②: near a singularity the guarded jog advances the EE less per step
    # than an un-guarded, full-speed jog from the same configuration. The jog assesses
    # the monitor after applying a step, so the guarded jog is primed with one step
    # first — that is the reactive one-step lag, not a missed damping.
    full = build_cartesian_jog()
    full.seed(_near_singular_state(_DAMPING_ELBOW))

    guarded = build_cartesian_jog()
    build_singularity_guard(guarded)
    guarded.seed(_near_singular_state(_DAMPING_ELBOW))
    guarded.step(_z_jog())
    assert guarded.velocity_scale < FULL_VELOCITY_SCALE

    full_start = full.current_pose("right")[:3].copy()
    full.step(_z_jog())
    full_delta = float(np.linalg.norm(full.current_pose("right")[:3] - full_start))

    guarded_start = guarded.current_pose("right")[:3].copy()
    guarded.step(_z_jog())
    guarded_delta = float(np.linalg.norm(guarded.current_pose("right")[:3] - guarded_start))

    assert guarded_delta < full_delta


def test_guard_holds_the_jog_below_the_floor() -> None:
    jog = build_cartesian_jog()
    guard = build_singularity_guard(jog)
    jog.seed(_near_singular_state(_CRITICAL_ELBOW))

    result = jog.step(_z_jog())
    assert result.stopped and result.reason is JogStopReason.SINGULARITY
    assert not result.committed
    assert guard.last_metrics is not None and guard.last_metrics.critical
    assert guard.last_warning is not None


def test_detach_restores_full_velocity_and_clears_the_monitor() -> None:
    jog = build_cartesian_jog()
    guard = build_singularity_guard(jog)
    jog.seed(_near_singular_state(_DAMPING_ELBOW))
    jog.step(_z_jog())
    assert jog.velocity_scale < FULL_VELOCITY_SCALE

    guard.detach()
    assert jog.velocity_scale == FULL_VELOCITY_SCALE
    # With the monitor cleared, a below-floor configuration no longer holds on singularity.
    jog.seed(_near_singular_state(_CRITICAL_ELBOW))
    result = jog.step(_z_jog())
    assert result.reason is not JogStopReason.SINGULARITY
