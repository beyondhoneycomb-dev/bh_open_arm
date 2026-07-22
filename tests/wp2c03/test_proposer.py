"""The proposal rules and their physics bounds (WP-2C-03, `12` FR-SAF-060 / 019).

Both `12` FR-SAF-060 rules are pure arithmetic over the collected statistics, so these tests
craft the statistics directly and assert the exact per-joint threshold. The two bounds of
`12` FR-SAF-019 — the ten-LSB floor below and the URDF effort cap above — are imported from
WP-1-06 and asserted against, never re-typed here, so the tests also prove the proposer reads
the single owned source rather than a copy.
"""

from __future__ import annotations

import pytest

from backend.safety_bringup.constants import ARM_JOINT_COUNT, URDF_EFFORT_LIMIT_NM
from backend.safety_bringup.thresholds import floor_for_joint
from backend.threshold_calib import (
    NOMINAL_SCALE_MAX,
    SIGMA_MULTIPLE,
    ProposalError,
    ResidualStats,
    propose_max_plus_sigma,
    propose_nominal_scaled,
)


def _stats(max_abs: tuple[float, ...], sigma: tuple[float, ...]) -> tuple[ResidualStats, ...]:
    """Build a full per-joint stats tuple from per-joint max and sigma."""
    return tuple(
        ResidualStats(
            joint_index=index,
            max_abs_nm=max_abs[index],
            sigma_nm=sigma[index],
            mean_nm=0.0,
            sample_count=1000,
        )
        for index in range(ARM_JOINT_COUNT)
    )


def test_max_plus_sigma_is_exact_when_unbounded() -> None:
    # An envelope well above the floor and below effort passes through as max + 3*sigma.
    max_abs = (1.0, 1.0, 0.8, 0.8, 0.3, 0.3, 0.3)
    sigma = (0.1, 0.1, 0.05, 0.05, 0.02, 0.02, 0.02)
    proposal = propose_max_plus_sigma(_stats(max_abs, sigma))
    for joint in proposal.per_joint:
        idx = joint.joint_index
        assert joint.raw_nm == pytest.approx(max_abs[idx] + SIGMA_MULTIPLE * sigma[idx])
        assert joint.effective_nm == pytest.approx(joint.raw_nm)
        assert not joint.floor_clamped
        assert not joint.effort_capped


def test_proposal_below_floor_is_raised_to_floor() -> None:
    # A near-zero collision-free residual proposes below the ten-LSB floor; it is raised to it.
    stats = _stats(max_abs=(0.01,) * ARM_JOINT_COUNT, sigma=(0.001,) * ARM_JOINT_COUNT)
    proposal = propose_max_plus_sigma(stats)
    for joint in proposal.per_joint:
        floor = floor_for_joint(joint.joint_index)
        assert joint.raw_nm < floor
        assert joint.floor_clamped
        assert joint.effective_nm == pytest.approx(floor)
        assert joint.effective_nm >= floor


def test_proposal_above_effort_is_capped() -> None:
    # A statistic beyond peak torque can never trip; it is lowered to the URDF effort cap.
    stats = _stats(max_abs=(100.0,) * ARM_JOINT_COUNT, sigma=(1.0,) * ARM_JOINT_COUNT)
    proposal = propose_max_plus_sigma(stats)
    for joint in proposal.per_joint:
        cap = URDF_EFFORT_LIMIT_NM[joint.joint_index]
        assert joint.effort_capped
        assert joint.effective_nm == pytest.approx(cap)


def test_nominal_scaled_is_exact() -> None:
    max_abs = (2.0, 2.0, 1.5, 1.5, 0.5, 0.5, 0.5)
    stats = _stats(max_abs, sigma=(0.1,) * ARM_JOINT_COUNT)
    proposal = propose_nominal_scaled(stats, NOMINAL_SCALE_MAX)
    for joint in proposal.per_joint:
        assert joint.raw_nm == pytest.approx(max_abs[joint.joint_index] * NOMINAL_SCALE_MAX)
        assert joint.effective_nm == pytest.approx(joint.raw_nm)


def test_nominal_scale_out_of_band_is_refused() -> None:
    stats = _stats(max_abs=(1.0,) * ARM_JOINT_COUNT, sigma=(0.1,) * ARM_JOINT_COUNT)
    with pytest.raises(ProposalError, match="outside"):
        propose_nominal_scaled(stats, 1.20)
    with pytest.raises(ProposalError, match="outside"):
        propose_nominal_scaled(stats, 1.00)


def test_effective_vector_matches_per_joint() -> None:
    stats = _stats(max_abs=(1.0,) * ARM_JOINT_COUNT, sigma=(0.1,) * ARM_JOINT_COUNT)
    proposal = propose_max_plus_sigma(stats)
    assert proposal.effective_nm() == tuple(j.effective_nm for j in proposal.per_joint)
    assert len(proposal.effective_nm()) == ARM_JOINT_COUNT
