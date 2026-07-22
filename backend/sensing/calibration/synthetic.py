"""Deterministic synthetic inputs for the offline calibration math (WP-3B-13).

3B has no camera, no board and no operator, so the calibration *solvers* are
exercised against synthetic correspondences instead — the same role
`contracts/fixtures/synthetic_camera` plays for the capture path. These generators
produce the *inputs* to the solvers (board point pairs, robot/target pose streams)
from a known ground truth; the solver then genuinely recovers that ground truth,
which is what the offline acceptance asserts.

This is not a faked result. A record built from these inputs is stamped
`CalibrationProvenance.SYNTHETIC` by its builder, and THE ONE RULE — never present
a synthetic intrinsic or extrinsic as a measured one — is upheld by that stamp plus
the deferral of the real capture to `reverify`. Nothing here writes a plausible
factory intrinsic; it writes board geometry and lets `cv2` do the solving.
"""

from __future__ import annotations

import cv2
import numpy as np
from numpy.typing import NDArray

from backend.sensing.calibration.handeye import HandEyeSetup
from backend.sensing.calibration.intrinsics import CameraIntrinsics, IntrinsicSource
from backend.sensing.calibration.transforms import make_transform


def _random_rotation(
    rng: np.random.Generator, min_angle: float, max_angle: float
) -> NDArray[np.float64]:
    """Return a random rotation matrix via a random axis and bounded angle."""
    axis = rng.normal(size=3)
    axis = axis / np.linalg.norm(axis)
    angle = rng.uniform(min_angle, max_angle)
    rotation, _ = cv2.Rodrigues(axis * angle)
    return np.asarray(rotation, dtype=np.float64)


def synthetic_ground_truth_transform(seed: int) -> NDArray[np.float64]:
    """Return a deterministic 4x4 ground-truth hand-eye transform for a seed.

    Args:
        seed: The RNG seed; the same seed yields the same transform.

    Returns:
        (NDArray) A 4x4 rigid transform to recover.
    """
    rng = np.random.default_rng(seed)
    rotation = _random_rotation(rng, 0.3, 1.2)
    translation = rng.uniform(-0.15, 0.15, size=3)
    return make_transform(rotation, translation)


def synthetic_hand_eye_poses(
    ground_truth: NDArray[np.float64],
    pose_count: int,
    setup: HandEyeSetup,
    seed: int,
) -> tuple[list[list[list[float]]], list[list[list[float]]]]:
    """Generate a pose set that recovers `ground_truth` under `setup`.

    A fixed target-in-base pose and a run of random gripper poses induce the
    matching target-to-camera poses for the chosen mounting geometry, so feeding
    the returned streams to `solve_hand_eye_all_methods` recovers `ground_truth`.

    Args:
        ground_truth: The 4x4 transform the solve should recover — camera-to-gripper
            for eye-in-hand, camera-to-base for eye-to-hand.
        pose_count: Number of sample poses to generate.
        setup: The mounting geometry.
        seed: The RNG seed for determinism.

    Returns:
        (tuple) `(robot_poses, target_poses)`, each a list of 4x4 nested-float
        matrices ready for `solve_hand_eye_all_methods`.
    """
    rng = np.random.default_rng(seed)
    # The two mounting geometries differ in which body is base-anchored. Eye-in-hand
    # anchors the target in base and rides the camera on the gripper. Eye-to-hand
    # anchors the camera in base and rides the target on the gripper through a
    # constant offset. The informative motion (the target sweeping the camera view)
    # must come from the gripper in both, or the solver has nothing to fit.
    target_in_base = make_transform(_random_rotation(rng, 0.2, 1.0), rng.uniform(0.2, 0.5, size=3))
    target_in_gripper = make_transform(
        _random_rotation(rng, 0.2, 1.0), rng.uniform(-0.05, 0.05, size=3)
    )

    robot_poses: list[list[list[float]]] = []
    target_poses: list[list[list[float]]] = []
    for _ in range(pose_count):
        robot = make_transform(_random_rotation(rng, 0.2, 1.2), rng.uniform(-0.3, 0.3, size=3))
        if setup is HandEyeSetup.EYE_IN_HAND:
            camera_in_base = robot @ ground_truth
            target_in_camera = np.linalg.inv(camera_in_base) @ target_in_base
        else:
            camera_in_base = ground_truth
            target_in_camera = np.linalg.inv(camera_in_base) @ (robot @ target_in_gripper)
        robot_poses.append([[float(v) for v in row] for row in robot])
        target_poses.append([[float(v) for v in row] for row in target_in_camera])
    return robot_poses, target_poses


def synthetic_intrinsics_ground_truth() -> CameraIntrinsics:
    """Return a deterministic ground-truth intrinsic used to synthesise board views.

    This is the intrinsic the synthetic board projection is generated *from*, so a
    calibration over those views recovers it. It is a generation parameter, not a
    stored result; a record built offline is marked synthetic by its builder.

    Returns:
        (CameraIntrinsics) The ground-truth intrinsic (VGA pinhole, mild distortion).
    """
    return CameraIntrinsics(
        fx=600.0,
        fy=600.0,
        cx=320.0,
        cy=240.0,
        distortion=(0.05, -0.02, 0.001, 0.0, 0.0),
        width=640,
        height=480,
        source=IntrinsicSource.CALIBRATION,
        rms_reprojection_error=None,
    )


def synthetic_board_views(
    intrinsics: CameraIntrinsics,
    board_cols: int,
    board_rows: int,
    square_size_m: float,
    view_count: int,
    seed: int,
) -> tuple[list[NDArray[np.float32]], list[NDArray[np.float32]]]:
    """Project a planar board through `intrinsics` from several viewpoints.

    Args:
        intrinsics: The ground-truth intrinsic to project through.
        board_cols: Inner corners per board row.
        board_rows: Inner corners per board column.
        square_size_m: Board square edge length in metres.
        view_count: Number of viewpoints to generate.
        seed: The RNG seed for determinism.

    Returns:
        (tuple) `(object_points, image_points)` for `calibrate_intrinsics`, each a
        list with one `float32` array per view.
    """
    rng = np.random.default_rng(seed)
    board = np.zeros((board_rows * board_cols, 3), dtype=np.float32)
    board[:, :2] = np.mgrid[0:board_cols, 0:board_rows].T.reshape(-1, 2) * square_size_m

    camera_matrix = intrinsics.camera_matrix()
    distortion = intrinsics.distortion_coefficients()

    object_points: list[NDArray[np.float32]] = []
    image_points: list[NDArray[np.float32]] = []
    for _ in range(view_count):
        axis = rng.normal(size=3)
        axis = axis / np.linalg.norm(axis)
        rvec = (axis * rng.uniform(0.1, 0.5)).astype(np.float64)
        tvec = np.array(
            [rng.uniform(-0.1, 0.1), rng.uniform(-0.1, 0.1), rng.uniform(0.4, 0.7)],
            dtype=np.float64,
        )
        projected, _ = cv2.projectPoints(board, rvec, tvec, camera_matrix, distortion)
        object_points.append(board.copy())
        image_points.append(projected.reshape(-1, 1, 2).astype(np.float32))
    return object_points, image_points
