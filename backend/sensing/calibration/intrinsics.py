"""Camera intrinsic lookup, store and checkerboard calibration (WP-3B-13).

`06` FR-CAM-023: an OpenCV/UVC webcam exposes no factory intrinsic query, so the
checkerboard/ChArUco calibration of FR-CAM-024 is the *sole* source of its
intrinsics. A RealSense camera has a factory path (`rs2_intrinsics`), but that
needs the device present and is deferred to the reverify hook; nothing here
fabricates a factory intrinsic for a camera that has none.

`calibrate_intrinsics` wraps `cv2.calibrateCamera` and carries its RMS reprojection
error on the result, which is the number FR-CAM-024 requires be surfaced. The
board-point correspondences are the input: real ones from a detected board on the
hardware path, deterministic synthetic ones on the offline path (`synthetic`).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

import cv2
import numpy as np
from numpy.typing import NDArray

from backend.sensing.calibration.constants import (
    DISTORTION_COEFFICIENT_COUNT,
    MIN_VIEWS_FOR_INTRINSIC,
)
from backend.sensing.calibration.errors import CalibrationInputError


class IntrinsicSource(Enum):
    """Where an intrinsic came from.

    `CALIBRATION` is the checkerboard solve — the only source for a UVC webcam
    (FR-CAM-023). `FACTORY_REALSENSE` is the device's own `rs2_intrinsics`, which
    requires the hardware and is produced only by the reverify hook, never invented
    here.
    """

    CALIBRATION = "calibration"
    FACTORY_REALSENSE = "factory_realsense"


@dataclass(frozen=True)
class CameraIntrinsics:
    """A camera's pinhole intrinsics, distortion and their provenance.

    Attributes:
        fx: Focal length in pixels, x.
        fy: Focal length in pixels, y.
        cx: Principal point x, pixels.
        cy: Principal point y, pixels.
        distortion: The five plumb-bob coefficients (k1, k2, p1, p2, k3).
        width: Image width the calibration was solved at, pixels.
        height: Image height the calibration was solved at, pixels.
        source: Whether this came from a calibration solve or a factory query.
        rms_reprojection_error: The calibration RMS reprojection error in pixels
            (FR-CAM-024), or None for a factory intrinsic that has no solve.
    """

    fx: float
    fy: float
    cx: float
    cy: float
    distortion: tuple[float, ...]
    width: int
    height: int
    source: IntrinsicSource
    rms_reprojection_error: float | None

    def camera_matrix(self) -> NDArray[np.float64]:
        """Return the 3x3 pinhole camera matrix K."""
        return np.array(
            [[self.fx, 0.0, self.cx], [0.0, self.fy, self.cy], [0.0, 0.0, 1.0]],
            dtype=np.float64,
        )

    def distortion_coefficients(self) -> NDArray[np.float64]:
        """Return the distortion coefficients as a row vector."""
        return np.asarray(self.distortion, dtype=np.float64)

    def to_dict(self) -> dict[str, Any]:
        """Serialise to plain types for the YAML record."""
        return {
            "fx": float(self.fx),
            "fy": float(self.fy),
            "cx": float(self.cx),
            "cy": float(self.cy),
            "distortion": [float(value) for value in self.distortion],
            "width": int(self.width),
            "height": int(self.height),
            "source": self.source.value,
            "rms_reprojection_error": (
                None if self.rms_reprojection_error is None else float(self.rms_reprojection_error)
            ),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CameraIntrinsics:
        """Rebuild from a YAML record payload.

        Args:
            data: The mapping produced by `to_dict`.

        Returns:
            (CameraIntrinsics) The reconstructed intrinsics.
        """
        rms = data.get("rms_reprojection_error")
        return cls(
            fx=float(data["fx"]),
            fy=float(data["fy"]),
            cx=float(data["cx"]),
            cy=float(data["cy"]),
            distortion=tuple(float(value) for value in data["distortion"]),
            width=int(data["width"]),
            height=int(data["height"]),
            source=IntrinsicSource(data["source"]),
            rms_reprojection_error=None if rms is None else float(rms),
        )


def calibrate_intrinsics(
    object_points: list[NDArray[np.float32]],
    image_points: list[NDArray[np.float32]],
    image_size: tuple[int, int],
) -> CameraIntrinsics:
    """Solve pinhole intrinsics from board correspondences (FR-CAM-024).

    Wraps `cv2.calibrateCamera`; the returned intrinsics carry its RMS reprojection
    error. This is the one intrinsic-solving path — the offline synthetic test and
    the real reverify hook both call it, differing only in where the board points
    come from.

    Args:
        object_points: Per-view board points in board coordinates, `(N, 3)` float32.
        image_points: Per-view detected image points, `(N, 1, 2)` or `(N, 2)` float32.
        image_size: The `(width, height)` the views were captured at.

    Returns:
        (CameraIntrinsics) The solved intrinsics with `source=CALIBRATION`.

    Raises:
        CalibrationInputError: If too few views are given or the per-view point
            counts do not match.
    """
    if len(object_points) < MIN_VIEWS_FOR_INTRINSIC:
        raise CalibrationInputError(
            f"intrinsic calibration needs at least {MIN_VIEWS_FOR_INTRINSIC} views, "
            f"got {len(object_points)}"
        )
    if len(object_points) != len(image_points):
        raise CalibrationInputError(
            f"object_points ({len(object_points)}) and image_points ({len(image_points)}) "
            "must have one entry per view"
        )

    width, height = image_size
    rms, camera_matrix, distortion, _rvecs, _tvecs = cv2.calibrateCamera(
        object_points, image_points, (width, height), None, None
    )
    coefficients = np.asarray(distortion, dtype=np.float64).reshape(-1)[
        :DISTORTION_COEFFICIENT_COUNT
    ]
    return CameraIntrinsics(
        fx=float(camera_matrix[0, 0]),
        fy=float(camera_matrix[1, 1]),
        cx=float(camera_matrix[0, 2]),
        cy=float(camera_matrix[1, 2]),
        distortion=tuple(float(value) for value in coefficients),
        width=int(width),
        height=int(height),
        source=IntrinsicSource.CALIBRATION,
        rms_reprojection_error=float(rms),
    )
