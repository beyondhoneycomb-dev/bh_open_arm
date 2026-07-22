"""Deferred real capture — the re-verification hook (plan 02a §4.1).

The real calibration *capture* needs a checkerboard/ChArUco, a real camera and an
operator moving the board; none exist on a desktop, so `test_real_capture_reverify`
skips with a reason until `OPENARM_CALIBRATION_REAL_FIXTURE` points at a capture
directory. The hook *machinery* is not deferred: `test_hook_reruns_the_solvers`
drives it over a capture in the real fixture format, proving it re-runs the identical
intrinsic and five-method hand-eye solvers rather than being a stub. The two together
are the honest shape — the machinery is exercised, only the real bytes are pending,
and the record is stamped REAL_CAPTURE so it is never mistaken for the synthetic path.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.sensing.calibration import (
    CalibrationProvenance,
    HandEyeSetup,
    fixture_dir_from_env,
)
from backend.sensing.calibration.reverify import reverify_from_fixture
from backend.sensing.calibration.synthetic import (
    synthetic_board_views,
    synthetic_ground_truth_transform,
    synthetic_hand_eye_poses,
    synthetic_intrinsics_ground_truth,
)


def _write_capture(fixture_dir: Path) -> None:
    """Write a capture directory in the real fixture format for one slot.

    The bytes are synthetic (there is no camera here), but the *format* is what a
    real capture supplies: board correspondences and pose streams the hook re-solves.
    """
    truth = synthetic_intrinsics_ground_truth()
    object_points, image_points = synthetic_board_views(truth, 9, 6, 0.025, 12, 1)
    ground_truth = synthetic_ground_truth_transform(2)
    robot_poses, target_poses = synthetic_hand_eye_poses(
        ground_truth, 12, HandEyeSetup.EYE_IN_HAND, 2
    )

    (fixture_dir / "binding.json").write_text(
        json.dumps({"front_rgb": {"camera_serial": "SER-9", "mount_id": "m1"}}),
        encoding="utf-8",
    )
    (fixture_dir / "intrinsics.json").write_text(
        json.dumps(
            {
                "front_rgb": {
                    "object_points": [view.tolist() for view in object_points],
                    "image_points": [view.tolist() for view in image_points],
                    "image_size": [truth.width, truth.height],
                }
            }
        ),
        encoding="utf-8",
    )
    (fixture_dir / "hand_eye.json").write_text(
        json.dumps(
            {
                "front_rgb": {
                    "setup": HandEyeSetup.EYE_IN_HAND.value,
                    "robot_poses": robot_poses,
                    "target_poses": target_poses,
                }
            }
        ),
        encoding="utf-8",
    )


def test_hook_reruns_the_solvers(tmp_path: Path) -> None:
    """The hook re-solves intrinsics and all five hand-eye methods over a capture."""
    _write_capture(tmp_path)

    report = reverify_from_fixture(tmp_path)

    assert set(report.records) == {"front_rgb"}
    record = report.records["front_rgb"]
    assert record.provenance is CalibrationProvenance.REAL_CAPTURE
    assert record.binding_key.camera_serial == "SER-9"
    assert record.intrinsics is not None
    assert record.intrinsics.rms_reprojection_error is not None
    assert record.hand_eye is not None
    assert len(record.hand_eye.solutions) == 5
    assert record.sample_pose_count == 12


def test_hook_requires_at_least_one_capture(tmp_path: Path) -> None:
    """An empty directory is refused rather than yielding a hollow record."""
    with pytest.raises(FileNotFoundError):
        reverify_from_fixture(tmp_path)


@pytest.mark.skipif(
    fixture_dir_from_env() is None,
    reason=(
        "deferred: needs a real checkerboard/ChArUco capture — a real camera, a "
        "physical board and an operator moving it, plus arm end-effector poses; set "
        "OPENARM_CALIBRATION_REAL_FIXTURE to a directory of intrinsics.json / "
        "hand_eye.json / binding.json"
    ),
)
def test_real_capture_reverify() -> None:
    """Re-verify against a real calibration capture, the moment one is supplied."""
    fixture_dir = fixture_dir_from_env()
    assert fixture_dir is not None
    report = reverify_from_fixture(fixture_dir)
    assert report.records, "real fixture directory declared no calibrated slots"
    for record in report.records.values():
        assert record.provenance is CalibrationProvenance.REAL_CAPTURE
        if record.hand_eye is not None:
            assert len(record.hand_eye.solutions) == 5
