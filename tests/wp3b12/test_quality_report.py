"""WP-3B-12 ③ — the quality report computes every listed metric, and exposes CAN drop.

`02b` §5.2 WP-3B-12 ③: loop rate, jitter, CAN drop, camera drop, missing, jerk and the
std floor. The CAN-drop measure must surface a `_batch_refresh` stale reuse rather than
let it pass as a fresh sample. ⑥: the gate bakes in no threshold — an ungated metric reads
UNSET, never a fabricated pass.
"""

from __future__ import annotations

import pytest

from backend.recorder.quality.metrics import (
    camera_drop_stats,
    can_drop_stats,
    jerk_stats,
    loop_timing,
    missing_samples,
    std_floor_stats,
)
from backend.recorder.quality.report import (
    FrameSample,
    GateOutcome,
    QualityThresholds,
    build_report,
    evaluate,
)
from contracts.capture import (
    CameraSlotKey,
    CaptureSidecar,
    CaptureSidecarRow,
    CaptureTimestamp,
    SensorSample,
    SlotCapture,
)
from contracts.fixtures.synthetic_dataset import build_synthetic_dataset
from tests.wp3b12.support import frames_from_dataset

_FIXTURE_FPS = 30.0


def test_report_on_synthetic_dataset_computes_every_metric() -> None:
    """③ Building a report over the synthetic dataset yields all seven measures populated."""
    dataset = build_synthetic_dataset(frame_count=8)
    report = build_report(frames_from_dataset(dataset), dataset.sidecar, dataset.config)

    assert report.frame_count == 8
    assert report.loop.rate_hz == pytest.approx(_FIXTURE_FPS)
    assert report.loop.jitter_std_s == pytest.approx(0.0, abs=1e-9)
    assert report.missing == 0
    # The synthetic action is a constant-velocity ramp, so its third derivative is zero.
    assert report.jerk.max_abs == pytest.approx(0.0, abs=1e-6)
    assert report.jerk.unit == "deg/s^3"
    # No drops are injected: every slot delivers every frame with a continuous counter.
    assert report.total_camera_drop() == 0
    assert len(report.camera_drop) == len(dataset.sidecar.slots())


def test_missing_samples_counts_frame_index_gaps() -> None:
    """③ A skipped frame index is counted as one missing sample."""
    assert missing_samples([0, 1, 2, 3]) == 0
    assert missing_samples([0, 1, 3, 4]) == 1
    assert missing_samples([0, 5]) == 4


def test_can_drop_is_exposed_not_hidden() -> None:
    """③ A recorder-flagged drop and a stale-state reuse are both surfaced."""
    states = [(1.0, 2.0), (1.0, 2.0), (3.0, 4.0), (3.0, 4.0)]
    flags = [False, True, False, False]

    stats = can_drop_stats(states, flags)

    assert stats.flagged_frames == 1
    assert stats.suspected_stale_frames == 2
    assert stats.total_frames == 4


def test_clean_stream_has_no_can_drop() -> None:
    """③ A stream whose state changes every frame reports no drop."""
    states = [(0.0,), (1.0,), (2.0,)]
    stats = can_drop_stats(states, [False, False, False])

    assert stats.flagged_frames == 0
    assert stats.suspected_stale_frames == 0


def test_camera_drop_counts_frame_number_gaps() -> None:
    """③ A gap in the device frame counter is reported as dropped frames for that slot."""
    slot = CameraSlotKey("left_wrist")
    numbers = [0, 1, 3, 4]  # frame 2 dropped by the device
    rows = tuple(
        CaptureSidecarRow(
            frame_index=i,
            slots={
                slot: SlotCapture(
                    capture_ts=CaptureTimestamp(1_000 + i * 100),
                    sensor=SensorSample(sensor_ts_ns=900 + i * 100, frame_number=n),
                )
            },
        )
        for i, n in enumerate(numbers)
    )
    sidecar = CaptureSidecar(episode_index=0, rows=rows)

    stats = camera_drop_stats(sidecar)

    assert len(stats) == 1
    assert stats[0].slot == "left_wrist"
    assert stats[0].frame_number_gaps == 1
    assert stats[0].missing_rows == 0


def test_jerk_zero_below_four_samples() -> None:
    """③ The third derivative is undefined below four frames and reports zero."""
    stats = jerk_stats([[0.0], [1.0], [3.0]], [0.0, 0.1, 0.2])
    assert stats.max_abs == 0.0


def test_jerk_detects_a_nonsmooth_command() -> None:
    """③ A position command with a jerk spike reports a nonzero magnitude."""
    positions = [[0.0], [0.0], [0.0], [10.0], [10.0], [10.0]]
    timestamps = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]

    stats = jerk_stats(positions, timestamps)

    assert stats.max_abs > 0.0


def test_std_floor_flags_stuck_channels_only_against_a_supplied_floor() -> None:
    """③⑥ A near-constant channel is flagged only when the caller supplies a floor."""
    states = [(0.0, 5.0), (0.0, 6.0), (0.0, 7.0)]  # channel 0 is stuck, channel 1 moves

    without_floor = std_floor_stats(states, floor=None)
    with_floor = std_floor_stats(states, floor=0.5)

    assert without_floor.below_floor == ()
    assert without_floor.min_std == pytest.approx(0.0)
    assert with_floor.below_floor == (0,)


def test_evaluate_reports_unset_without_thresholds() -> None:
    """⑥ With no thresholds every metric is UNSET — never a fabricated pass."""
    dataset = build_synthetic_dataset(frame_count=8)
    report = build_report(frames_from_dataset(dataset), dataset.sidecar, dataset.config)

    outcomes = evaluate(report, QualityThresholds())

    assert set(outcomes.values()) == {GateOutcome.UNSET}


def test_evaluate_grades_against_supplied_thresholds() -> None:
    """⑥ Supplied thresholds produce PASS/FAIL; the seam a measured bar is injected through."""
    dataset = build_synthetic_dataset(frame_count=8)
    report = build_report(frames_from_dataset(dataset), dataset.sidecar, dataset.config)

    outcomes = evaluate(
        report,
        QualityThresholds(min_loop_rate_hz=25.0, max_missing_samples=0, max_jerk=1.0),
    )

    assert outcomes["loop_rate"] is GateOutcome.PASS
    assert outcomes["missing"] is GateOutcome.PASS
    assert outcomes["jerk"] is GateOutcome.PASS
    assert outcomes["jitter"] is GateOutcome.UNSET


def test_loop_timing_needs_two_frames() -> None:
    """③ A single frame yields a defined, zeroed timing rather than a division error."""
    timing = loop_timing([0.0])
    assert timing.rate_hz == 0.0


def test_frame_sample_defaults_can_stale_false() -> None:
    """The recorder-supplied CAN flag defaults off when the recorder provides none."""
    sample = FrameSample(
        frame_index=0, timestamp=0.0, action={"m.pos": 0.0}, observation_state=(0.0,)
    )
    assert sample.can_stale is False
