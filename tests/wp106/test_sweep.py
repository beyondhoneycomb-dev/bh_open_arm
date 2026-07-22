"""Acceptance ⑨-a ⑨-b: the sweep publication gate — three constraints, or no artifact.

These exercise the *gate* offline: the three-constraint refusal and the zero-commands-over-
limiter check. No tracking-pass verdict is produced here — the measured column is absent
offline, so the tracking vector is empty and the real command-following sweep stays deferred.
"""

from __future__ import annotations

import pytest

from backend.safety_bringup import (
    SweepConstraints,
    SweepPublicationRefusedError,
    SweepSample,
    assert_sweep_publishable,
    bootstrap_limiter_rad_s,
)

_JOINT = 2  # a DM4340 joint; bootstrap limiter 3.14 rad/s.


def _all_constraints() -> SweepConstraints:
    return SweepConstraints(single_joint=True, mechanically_constrained=True)


def _under_limiter_samples() -> tuple[SweepSample, ...]:
    limiter = bootstrap_limiter_rad_s()[_JOINT]
    return tuple(
        SweepSample(commanded_rad_s=limiter * fraction, measured_rad_s=None)
        for fraction in (0.1, 0.5, 0.9, 1.0)
    )


def test_sweep_publishable_under_all_constraints() -> None:
    # ⑨-a: single joint, mechanically constrained, all commands under the limiter => admitted.
    publication = assert_sweep_publishable(_JOINT, _under_limiter_samples(), _all_constraints())
    assert publication.commands_over_limiter == 0
    assert publication.limiter_rad_s == bootstrap_limiter_rad_s()[_JOINT]


def test_offline_sweep_produces_no_tracking_verdict() -> None:
    # ⑨-b: with no measured column the tracking vector is empty — the verdict is deferred.
    publication = assert_sweep_publishable(_JOINT, _under_limiter_samples(), _all_constraints())
    assert publication.tracking_error_rad_s == ()


def test_multi_joint_sweep_is_refused() -> None:
    # ⑨-a: dropping the single-joint constraint refuses publication.
    constraints = SweepConstraints(single_joint=False, mechanically_constrained=True)
    with pytest.raises(SweepPublicationRefusedError, match="single-joint"):
        assert_sweep_publishable(_JOINT, _under_limiter_samples(), constraints)


def test_unconstrained_reach_sweep_is_refused() -> None:
    # ⑨-a: dropping the mechanical-constraint refuses publication.
    constraints = SweepConstraints(single_joint=True, mechanically_constrained=False)
    with pytest.raises(SweepPublicationRefusedError, match="mechanically constrained"):
        assert_sweep_publishable(_JOINT, _under_limiter_samples(), constraints)


def test_command_over_limiter_is_refused() -> None:
    # ⑨-a/⑨-b: a command above the bootstrap limiter is refused — raising it is self-approval.
    limiter = bootstrap_limiter_rad_s()[_JOINT]
    samples = (SweepSample(commanded_rad_s=limiter * 1.01, measured_rad_s=None),)
    with pytest.raises(SweepPublicationRefusedError, match="exceed the bootstrap limiter"):
        assert_sweep_publishable(_JOINT, samples, _all_constraints())
