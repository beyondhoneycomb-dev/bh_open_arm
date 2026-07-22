"""The per-joint exciting trajectory: limit-respecting and index-addressable.

A spec whose peak position excursion or peak velocity leaves a joint's bounds is refused
at construction; every sample is a pure function of its index, which is what makes a
resume from a recorded trajectory index reproduce the aborted run's sample exactly.
"""

from __future__ import annotations

import pytest

from backend.dynamics import ARM_JOINT_COUNT
from backend.excitation import (
    ExcitingTrajectory,
    JointBounds,
    JointExcitation,
    TrajectoryLimitError,
    design_band,
)
from tests.wp2b06.support import ARM_BOUNDS, REST_POSE, build_trajectory


def test_sample_count_is_duration_times_rate() -> None:
    trajectory = build_trajectory(logging_frequency_hz=1000.0, duration_s=0.02)
    assert trajectory.sample_count == 20


def test_sample_is_a_pure_function_of_index() -> None:
    # Re-sampling an index gives an identical result — the resume-by-index guarantee.
    trajectory = build_trajectory()
    assert trajectory.sample(7) == trajectory.sample(7)


def test_resume_index_reproduces_the_forward_sample() -> None:
    # The sample reached by resuming at index 5 is the one a full run would command there.
    trajectory = build_trajectory()
    forward = [trajectory.sample(i) for i in range(trajectory.sample_count)]
    assert trajectory.sample(5) == forward[5]


def test_index_out_of_range_refused() -> None:
    trajectory = build_trajectory()
    with pytest.raises(IndexError):
        trajectory.sample(trajectory.sample_count)


def test_position_excursion_leaving_bounds_refused() -> None:
    # An amplitude larger than the joint's headroom is refused before any command.
    band = design_band(1000.0)
    joints = [JointExcitation(center_rad=0.0, amplitude_rad=0.0) for _ in range(ARM_JOINT_COUNT)]
    joints[3] = JointExcitation(center_rad=0.1, amplitude_rad=0.5)  # joint4 low bound is 0.0
    with pytest.raises(TrajectoryLimitError, match="joint 3"):
        ExcitingTrajectory(band=band, joints=joints, bounds=list(ARM_BOUNDS), duration_s=0.02)


def test_peak_velocity_over_bound_refused() -> None:
    # A tight speed ceiling rejects a spec whose summed tone velocities exceed it.
    band = design_band(1000.0)
    joints = [
        JointExcitation(center_rad=REST_POSE[i], amplitude_rad=0.05) for i in range(ARM_JOINT_COUNT)
    ]
    tight = list(ARM_BOUNDS)
    tight[0] = JointBounds(ARM_BOUNDS[0].position_min_rad, ARM_BOUNDS[0].position_max_rad, 0.01)
    with pytest.raises(TrajectoryLimitError, match="peak velocity"):
        ExcitingTrajectory(band=band, joints=joints, bounds=tight, duration_s=0.02)


def test_wrong_joint_count_refused() -> None:
    band = design_band(1000.0)
    joints = [JointExcitation(0.0, 0.0) for _ in range(ARM_JOINT_COUNT - 1)]
    with pytest.raises(ValueError, match="joints and bounds"):
        ExcitingTrajectory(band=band, joints=joints, bounds=list(ARM_BOUNDS), duration_s=0.02)


def test_peak_velocity_is_positive_for_excited_joint() -> None:
    trajectory = build_trajectory()
    assert trajectory.peak_velocity_rad_s(0) > 0.0
