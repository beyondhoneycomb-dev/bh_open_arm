"""Rigid-transform helpers shared by the hand-eye solver and its residual math.

A rigid transform is a 4x4 homogeneous `float64` matrix. These are pure NumPy so
the deviation and residual arithmetic (rotation in degrees, translation in
millimetres) has one definition that both the live solve and the reverify hook
call. The unit convention is fixed in `constants`: translation columns are metres,
deviations are reported in millimetres.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from backend.sensing.calibration.constants import MM_PER_METRE

# A rotation matrix whose trace maps just outside [-1, 3] under floating-point
# error would push arccos out of domain; the angle formula clamps to this range.
_TRACE_ARG_MIN = -1.0
_TRACE_ARG_MAX = 1.0

TransformRows = tuple[
    tuple[float, float, float, float],
    tuple[float, float, float, float],
    tuple[float, float, float, float],
    tuple[float, float, float, float],
]


def make_transform(
    rotation: NDArray[np.float64], translation: NDArray[np.float64]
) -> NDArray[np.float64]:
    """Assemble a 4x4 homogeneous transform from a 3x3 rotation and a 3-vector.

    Args:
        rotation: A 3x3 rotation matrix.
        translation: A length-3 translation, in metres.

    Returns:
        (NDArray) The 4x4 homogeneous transform.
    """
    transform = np.eye(4, dtype=np.float64)
    transform[:3, :3] = rotation
    transform[:3, 3] = np.asarray(translation, dtype=np.float64).reshape(3)
    return transform


def rotation_of(transform: NDArray[np.float64]) -> NDArray[np.float64]:
    """Return the 3x3 rotation block of a homogeneous transform."""
    return np.asarray(transform, dtype=np.float64)[:3, :3]


def translation_of(transform: NDArray[np.float64]) -> NDArray[np.float64]:
    """Return the length-3 translation column of a homogeneous transform, in metres."""
    return np.asarray(transform, dtype=np.float64)[:3, 3]


def invert(transform: NDArray[np.float64]) -> NDArray[np.float64]:
    """Invert a rigid transform using the rotation transpose, not a general solve.

    A rigid inverse is exact and cheap — `R.T` for rotation, `-R.T @ t` for
    translation — where a general `np.linalg.inv` would introduce avoidable error
    that the residual arithmetic then reads as a spurious disagreement.

    Args:
        transform: A 4x4 homogeneous rigid transform.

    Returns:
        (NDArray) The inverse transform.
    """
    rotation = rotation_of(transform)
    translation = translation_of(transform)
    inverse = np.eye(4, dtype=np.float64)
    inverse[:3, :3] = rotation.T
    inverse[:3, 3] = -rotation.T @ translation
    return inverse


def rotation_angle_deg(rotation: NDArray[np.float64]) -> float:
    """Return the axis-angle magnitude of a rotation matrix, in degrees.

    Args:
        rotation: A 3x3 rotation matrix.

    Returns:
        (float) The rotation angle in degrees, in [0, 180].
    """
    trace = float(np.trace(np.asarray(rotation, dtype=np.float64)))
    cosine = np.clip((trace - 1.0) / 2.0, _TRACE_ARG_MIN, _TRACE_ARG_MAX)
    return float(np.degrees(np.arccos(cosine)))


def relative_rotation_deg(a: NDArray[np.float64], b: NDArray[np.float64]) -> float:
    """Return the angle between two rotation matrices, in degrees.

    The relative rotation `a.T @ b` has an axis-angle magnitude that is the
    geodesic distance on SO(3); that magnitude is the rotation deviation
    `06` FR-CAM-026 reports between two hand-eye solutions.

    Args:
        a: A 3x3 rotation matrix.
        b: A 3x3 rotation matrix.

    Returns:
        (float) The angle between them in degrees, in [0, 180].
    """
    return rotation_angle_deg(np.asarray(a, dtype=np.float64).T @ np.asarray(b, dtype=np.float64))


def translation_distance_mm(a: NDArray[np.float64], b: NDArray[np.float64]) -> float:
    """Return the Euclidean distance between two metre-valued translations, in mm.

    Args:
        a: A length-3 translation in metres.
        b: A length-3 translation in metres.

    Returns:
        (float) The distance in millimetres.
    """
    delta = np.asarray(a, dtype=np.float64).reshape(3) - np.asarray(b, dtype=np.float64).reshape(3)
    return float(np.linalg.norm(delta) * MM_PER_METRE)


def to_rows(transform: NDArray[np.float64]) -> list[list[float]]:
    """Serialise a 4x4 transform to nested plain floats for the YAML record.

    Args:
        transform: A 4x4 homogeneous transform.

    Returns:
        (list[list[float]]) The 4x4 matrix as row-major Python floats.
    """
    matrix = np.asarray(transform, dtype=np.float64).reshape(4, 4)
    return [[float(value) for value in row] for row in matrix]


def from_rows(rows: object) -> NDArray[np.float64]:
    """Rebuild a 4x4 transform from the nested floats a YAML record stored.

    Args:
        rows: A 4x4 nested sequence of numbers.

    Returns:
        (NDArray) The 4x4 homogeneous transform.

    Raises:
        ValueError: If the payload is not 4x4.
    """
    matrix = np.asarray(rows, dtype=np.float64)
    if matrix.shape != (4, 4):
        raise ValueError(f"transform must be 4x4, got shape {matrix.shape}")
    return matrix
