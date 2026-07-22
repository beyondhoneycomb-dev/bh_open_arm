"""The residual collector recovers per-joint max and sigma by streaming (WP-2C-03).

`12` FR-SAF-060 has the wizard run a trajectory repeatedly and collect the residual max and
sigma. The collector's contract is that folding runs in one at a time yields exactly what a
batch computation over the concatenated samples would, at constant memory — so these tests
compare its streaming result against numpy over the concatenation, and hold the guards that
refuse a statistic no sample can support.
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.safety_bringup.constants import ARM_JOINT_COUNT
from backend.threshold_calib import (
    CollectorError,
    collector_for_arm,
    synthetic_residual_run,
    synthetic_truth,
)


def test_streaming_equals_batch() -> None:
    # Folding runs in one at a time equals a batch max/sigma over the concatenation.
    runs = [synthetic_residual_run(i) for i in range(5)]
    collector = collector_for_arm()
    for run in runs:
        collector.add_run(run)

    batch = np.concatenate(runs, axis=0)
    expected_max = np.abs(batch).max(axis=0)
    expected_sigma = batch.std(axis=0, ddof=1)
    expected_mean = batch.mean(axis=0)

    stats = collector.stats()
    assert len(stats) == ARM_JOINT_COUNT
    assert collector.run_count() == 5
    for joint, stat in enumerate(stats):
        assert stat.max_abs_nm == pytest.approx(expected_max[joint], abs=1e-12)
        assert stat.sigma_nm == pytest.approx(expected_sigma[joint], rel=1e-9)
        assert stat.mean_nm == pytest.approx(expected_mean[joint], abs=1e-9)
        assert stat.sample_count == batch.shape[0]


def test_sample_sigma_converges_to_generating_sigma() -> None:
    # The collected sample sigma tracks the generating sigma the stream was drawn at.
    collector = collector_for_arm()
    for i in range(40):
        collector.add_run(synthetic_residual_run(i))
    truth = synthetic_truth()
    for stat in collector.stats():
        assert stat.sigma_nm == pytest.approx(truth.sigma_nm[stat.joint_index], rel=0.1)


def test_max_is_magnitude_not_signed() -> None:
    # A large negative residual sets the max magnitude; the collector tracks |r|, not r.
    collector = collector_for_arm()
    run = np.zeros((4, ARM_JOINT_COUNT), dtype=np.float64)
    run[0, 2] = -3.0
    run[1, 2] = 0.5
    collector.add_run(run)
    collector.add_run(run)
    assert collector.stats()[2].max_abs_nm == pytest.approx(3.0, abs=1e-12)


def test_stats_below_min_runs_is_refused() -> None:
    collector = collector_for_arm()
    collector.add_run(synthetic_residual_run(0))
    with pytest.raises(CollectorError, match="at least .* runs"):
        collector.stats()


def test_wrong_joint_width_is_refused() -> None:
    collector = collector_for_arm()
    with pytest.raises(CollectorError, match="n_samples"):
        collector.add_run(np.zeros((10, ARM_JOINT_COUNT + 1), dtype=np.float64))


def test_empty_run_is_refused() -> None:
    collector = collector_for_arm()
    with pytest.raises(CollectorError, match="no samples"):
        collector.add_run(np.zeros((0, ARM_JOINT_COUNT), dtype=np.float64))
