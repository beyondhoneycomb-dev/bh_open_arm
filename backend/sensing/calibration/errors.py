"""Calibration contract refusals (WP-3B-13).

These are contract/configuration violations, not runtime `OA-*` conditions, so —
like `CameraRegistryError` in `CTR-CAM@v1` — they raise directly rather than being
wrapped in an `ErrorEnvelope`. A stale calibration allowed to start collection is
`06`'s `FAIL_BLOCKING` branch, and `CollectionBlockedError` is the shape that
branch takes in code: the collect-block is a raised refusal that cannot be caught
and continued past silently.
"""

from __future__ import annotations


class CalibrationError(ValueError):
    """Base class for a calibration contract violation."""


class CalibrationInputError(CalibrationError):
    """A solver was handed malformed input (mismatched or too-few pose/view sets)."""


class CollectionBlockedError(CalibrationError):
    """Collection start is refused because a camera's calibration is not usable.

    `06` FR-CAM-028 requires that a stale or missing calibration *block* the start
    of data collection. This is that block; catching it to proceed anyway is the
    `FAIL_BLOCKING` violation the acceptance forbids.
    """


class StaleCalibrationError(CollectionBlockedError):
    """The stored calibration was captured under a different rigid relationship.

    A serial swap, slot reassignment or mount reattach changes the camera-to-end-
    effector rigid body, so the prior extrinsic no longer describes it (FR-CAM-028).
    """


class MissingCalibrationError(CollectionBlockedError):
    """No calibration is stored for a camera whose intrinsics have no factory source.

    An OpenCV webcam has no factory intrinsic path, so calibration is the sole
    source (FR-CAM-023); its absence blocks collection rather than defaulting.
    """
