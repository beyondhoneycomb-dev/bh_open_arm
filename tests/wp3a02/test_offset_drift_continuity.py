"""WP-3A-02 ③ — host↔sensor offset/drift and frame-number continuity are verified.

`02b` §5.2 WP-3A-02 ③ requires that, on a device exposing a hardware clock and a
frame counter, the host↔sensor offset and its drift, and the continuity of the
frame numbers, are actually checked. These tests drive the verifiers over synthetic
sidecars (a steady offset with zero drift, a drifting offset, a continuous counter,
a counter with a gap), then exercise the re-verification hook end to end over a
fixture directory. The real-device leg is deferred behind `OPENARM_CAP_REAL_FIXTURE`
because it needs a RealSense capture this environment does not have; the machinery
is proven here, only the hardware bytes are pending.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import contracts.capture as cap
from contracts.capture.reverify import fixture_dir_from_env, reverify_from_fixture

SLOT = cap.CameraSlotKey("left_wrist")


def _sidecar(offsets: list[int], frame_numbers: list[int]) -> cap.CaptureSidecar:
    """Build a one-slot sidecar with given host↔sensor offsets and frame numbers.

    The capture instant is a fixed cadence; the sensor timestamp is offset behind
    it by the requested per-frame offset, so `host_sensor_offsets` recovers exactly
    the input offsets.
    """
    rows = []
    for i, (offset, number) in enumerate(zip(offsets, frame_numbers, strict=True)):
        capture_ns = 1_000 + i * 100
        rows.append(
            cap.CaptureSidecarRow(
                frame_index=i,
                slots={
                    SLOT: cap.SlotCapture(
                        cap.CaptureTimestamp(capture_ns),
                        cap.SensorSample(sensor_ts_ns=capture_ns - offset, frame_number=number),
                    )
                },
            )
        )
    return cap.CaptureSidecar(episode_index=0, rows=tuple(rows))


def test_steady_offset_has_zero_drift() -> None:
    """A constant host↔sensor offset yields the offset series and zero drift."""
    sidecar = _sidecar(offsets=[500, 500, 500], frame_numbers=[1, 2, 3])
    assert cap.host_sensor_offsets(sidecar, SLOT) == [500, 500, 500]
    assert cap.offset_drift_span(cap.host_sensor_offsets(sidecar, SLOT)) == 0


def test_drifting_offset_reports_its_peak_to_peak_span() -> None:
    """A drifting offset is measured as its peak-to-peak span in nanoseconds."""
    sidecar = _sidecar(offsets=[500, 520, 480, 560], frame_numbers=[1, 2, 3, 4])
    assert cap.offset_drift_span(cap.host_sensor_offsets(sidecar, SLOT)) == 80


def test_continuous_frame_numbers_pass() -> None:
    """A frame counter that increments by one each step is continuous."""
    sidecar = _sidecar(offsets=[0, 0, 0, 0], frame_numbers=[10, 11, 12, 13])
    assert cap.frame_numbers_continuous(cap.slot_frame_numbers(sidecar, SLOT)) is True


def test_a_gap_in_frame_numbers_breaks_continuity() -> None:
    """A skipped frame number is a dropped frame the continuity check must surface."""
    sidecar = _sidecar(offsets=[0, 0, 0], frame_numbers=[10, 12, 13])
    assert cap.frame_numbers_continuous(cap.slot_frame_numbers(sidecar, SLOT)) is False


def test_a_slot_without_hardware_yields_empty_series() -> None:
    """A plain webcam slot yields no offset or frame-number series, never a fake zero."""
    scene = cap.CameraSlotKey("scene")
    rows = (
        cap.CaptureSidecarRow(0, {scene: cap.SlotCapture(cap.CaptureTimestamp(1), None)}),
        cap.CaptureSidecarRow(1, {scene: cap.SlotCapture(cap.CaptureTimestamp(2), None)}),
    )
    sidecar = cap.CaptureSidecar(episode_index=0, rows=rows)
    assert cap.host_sensor_offsets(sidecar, scene) == []
    assert cap.slot_frame_numbers(sidecar, scene) == []


# --- the re-verification hook ------------------------------------------------


def _write_fixture(fixture_dir: Path, sidecar: cap.CaptureSidecar, expected: dict) -> None:
    """Write the sidecar records and the expectation into a fixture directory."""
    (fixture_dir / "sidecar.json").write_text(
        json.dumps(
            {
                "episode_index": sidecar.episode_index,
                "records": cap.sidecar_to_records(sidecar),
            }
        ),
        encoding="utf-8",
    )
    (fixture_dir / "expected.json").write_text(json.dumps(expected), encoding="utf-8")


def test_hook_reverifies_a_matching_capture(tmp_path: Path) -> None:
    """The hook reloads a capture and confirms the drift bound and continuity hold."""
    sidecar = _sidecar(offsets=[500, 520, 480], frame_numbers=[1, 2, 3])
    _write_fixture(
        tmp_path,
        sidecar,
        {"slots": {SLOT.value: {"max_offset_drift_ns": 100, "frame_numbers_continuous": True}}},
    )
    results = reverify_from_fixture(tmp_path)
    assert len(results) == 1
    assert results[0].matched, results[0].detail
    assert results[0].offset_drift_ns == 40
    assert results[0].continuous is True


def test_hook_reports_a_drift_or_continuity_mismatch(tmp_path: Path) -> None:
    """A capture that violates the drift bound or continuity is reported, not passed."""
    sidecar = _sidecar(offsets=[500, 900], frame_numbers=[1, 3])
    _write_fixture(
        tmp_path,
        sidecar,
        {"slots": {SLOT.value: {"max_offset_drift_ns": 100, "frame_numbers_continuous": True}}},
    )
    results = reverify_from_fixture(tmp_path)
    assert results and not results[0].matched
    assert "drift" in results[0].detail
    assert "continuity" in results[0].detail


def test_hook_revalidates_sidecar_shape(tmp_path: Path) -> None:
    """A fixture whose frame_index is not the contiguous join key is rejected on reload."""
    (tmp_path / "sidecar.json").write_text(
        json.dumps(
            {
                "episode_index": 0,
                "records": [
                    {"episode_index": 0, "frame_index": 0, "left_wrist_capture_ts": 1},
                    {"episode_index": 0, "frame_index": 5, "left_wrist_capture_ts": 2},
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "expected.json").write_text(json.dumps({"slots": {}}), encoding="utf-8")
    with pytest.raises(cap.CaptureContractError):
        reverify_from_fixture(tmp_path)


@pytest.mark.skipif(
    fixture_dir_from_env() is None,
    reason=(
        "deferred: needs a real RealSense capture exposing hardware timestamps and "
        "frame numbers; set OPENARM_CAP_REAL_FIXTURE to a directory of sidecar.json + "
        "expected.json"
    ),
)
def test_real_device_reverify() -> None:
    """Re-verify against a real-device capture the moment one is supplied."""
    fixture_dir = fixture_dir_from_env()
    assert fixture_dir is not None
    results = reverify_from_fixture(fixture_dir)
    assert results, "real fixture declared no slots"
    for result in results:
        assert result.matched, f"{result.slot}: {result.detail}"
