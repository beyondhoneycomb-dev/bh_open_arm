"""Acceptance ② — intrinsic store/lookup and the YAML round-trip.

`02b` WP-3B-13 ②: the calibration YAML persists the performed-at time, camera
serial, slot key, sample-pose count, per-method results and residuals, and reloads
identically. `06` FR-CAM-023/024: a UVC webcam has no factory intrinsic, so the
calibration solve is the sole source, and it carries the RMS reprojection error.
"""

from __future__ import annotations

from pathlib import Path

from backend.sensing.calibration import (
    CalibrationBindingKey,
    CalibrationProvenance,
    CalibrationRecord,
    CalibrationStore,
    HandEyeSetup,
    IntrinsicSource,
    calibrate_intrinsics,
    solve_hand_eye_all_methods,
)
from backend.sensing.calibration.persistence import (
    load_calibration_record,
    save_calibration_record,
)
from backend.sensing.calibration.synthetic import (
    synthetic_board_views,
    synthetic_ground_truth_transform,
    synthetic_hand_eye_poses,
    synthetic_intrinsics_ground_truth,
)


def _build_record(slot_key: str, seed: int) -> CalibrationRecord:
    """Build a full calibration record from synthetic inputs."""
    truth = synthetic_intrinsics_ground_truth()
    object_points, image_points = synthetic_board_views(truth, 9, 6, 0.025, 15, seed)
    intrinsics = calibrate_intrinsics(object_points, image_points, (truth.width, truth.height))

    ground_truth = synthetic_ground_truth_transform(seed)
    robot_poses, target_poses = synthetic_hand_eye_poses(
        ground_truth, 12, HandEyeSetup.EYE_IN_HAND, seed
    )
    hand_eye = solve_hand_eye_all_methods(robot_poses, target_poses, HandEyeSetup.EYE_IN_HAND)

    return CalibrationRecord(
        performed_at="2026-07-22T00:00:00+00:00",
        binding_key=CalibrationBindingKey(
            camera_serial="SER-123", slot_key=slot_key, mount_id="mount-a"
        ),
        sample_pose_count=hand_eye.sample_pose_count,
        provenance=CalibrationProvenance.SYNTHETIC,
        hand_eye=hand_eye,
        intrinsics=intrinsics,
    )


def test_intrinsic_solve_is_sole_source_and_carries_rms() -> None:
    """A webcam intrinsic comes only from the calibration solve, with an RMS error."""
    truth = synthetic_intrinsics_ground_truth()
    object_points, image_points = synthetic_board_views(truth, 9, 6, 0.025, 15, 1)

    intrinsics = calibrate_intrinsics(object_points, image_points, (truth.width, truth.height))

    assert intrinsics.source is IntrinsicSource.CALIBRATION
    assert intrinsics.rms_reprojection_error is not None
    assert intrinsics.rms_reprojection_error >= 0.0
    assert abs(intrinsics.fx - truth.fx) < 1.0
    assert abs(intrinsics.cy - truth.cy) < 1.0


def test_yaml_round_trip_preserves_the_whole_record(tmp_path: Path) -> None:
    """Persist then reload; every FR-CAM-027 field survives byte-for-byte in value."""
    record = _build_record("front_rgb", 5)
    path = tmp_path / "front_rgb.oa_calibration.yaml"

    save_calibration_record(path, record)
    reloaded = load_calibration_record(path)

    assert reloaded.performed_at == record.performed_at
    assert reloaded.binding_key == record.binding_key
    assert reloaded.sample_pose_count == record.sample_pose_count
    assert reloaded.provenance is CalibrationProvenance.SYNTHETIC
    assert reloaded.intrinsics == record.intrinsics
    assert reloaded.hand_eye is not None and record.hand_eye is not None
    assert reloaded.hand_eye.methods() == record.hand_eye.methods()
    assert reloaded.hand_eye.solutions == record.hand_eye.solutions
    assert reloaded.hand_eye.deviations == record.hand_eye.deviations


def test_store_lookup_returns_saved_record(tmp_path: Path) -> None:
    """The store persists a record and looks it up by slot key."""
    store = CalibrationStore(directory=tmp_path)
    record = _build_record("wrist_left_rgb", 8)

    store.save(record)
    looked_up = store.lookup("wrist_left_rgb")

    assert looked_up is not None
    assert looked_up.slot_key == "wrist_left_rgb"
    assert looked_up.binding_key == record.binding_key
    assert looked_up.intrinsics == record.intrinsics


def test_store_lookup_missing_slot_is_none(tmp_path: Path) -> None:
    """A slot with no stored record looks up as None, not an error."""
    store = CalibrationStore(directory=tmp_path)
    assert store.lookup("never_calibrated") is None


def test_save_stamps_performed_at_when_absent(tmp_path: Path) -> None:
    """An empty performed-at is stamped at write time (FR-CAM-027 수행 일시)."""
    record = _build_record("front_rgb", 6)
    from dataclasses import replace

    unstamped = replace(record, performed_at="")
    path = tmp_path / "front_rgb.oa_calibration.yaml"

    written = save_calibration_record(path, unstamped)

    assert written.performed_at
    assert load_calibration_record(path).performed_at == written.performed_at
