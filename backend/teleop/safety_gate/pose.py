"""The EE pose the safety gate guards, and the 3x3 rotation math it is checked with.

`WP-3B-10` operates on the end-effector target as a base-frame homogeneous pose: a
3x3 rotation matrix and a 3-vector translation in metres (`05` §2.8 fixes the robot
base frame and the rotation-matrix convention, `det = +1` for a proper rotation).
The pose is kept as plain nested tuples rather than a numpy array so the whole
module stays in the AI-offline light lane with no array dependency, and so every
safety decision is a line of arithmetic an auditor can read.

The rotation helpers here are the ones the two safety checks need and nothing more:
`determinant` and `is_finite_pose` back the pose-sanity discard (`FR-TEL-038`), and
`geodesic_angle` plus `clamp_rotation_toward` back the angular half of the EE
velocity limit (`FR-TEL-037`). None of them mutate their inputs; an `EEPose` is
frozen, so a filtered pose is always a new value.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# A 3x3 matrix and a 3-vector as immutable nested tuples. The row-major layout
# matches the `05` §2.8 `R_ROBOT` literal, so a reader can compare directly.
Matrix3 = tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]
Vector3 = tuple[float, float, float]

# The identity rotation, used as the default orientation of a seed pose.
IDENTITY_ROTATION: Matrix3 = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))

# Below this the axis of a relative rotation is numerically undefined (sin θ → 0),
# so an angular clamp cannot pick a direction to rotate along. At θ this small the
# angular speed is far under any limit, so the clamp is a no-op and the target is
# returned unchanged; the guard only avoids a divide-by-zero.
_AXIS_SINGULAR_EPS = 1e-9


@dataclass(frozen=True)
class EEPose:
    """One end-effector target pose: a base-frame rotation and translation.

    Attributes:
        rotation: The 3x3 base-frame rotation matrix, row-major. A proper rotation
            has determinant `+1`; a degenerate frame has determinant near zero,
            which the pose-sanity check discards (`FR-TEL-038`).
        translation: The base-frame position `(x, y, z)` in metres.
    """

    rotation: Matrix3
    translation: Vector3


def vector_sub(left: Vector3, right: Vector3) -> Vector3:
    """Return `left - right` componentwise."""
    return (left[0] - right[0], left[1] - right[1], left[2] - right[2])


def vector_add(left: Vector3, right: Vector3) -> Vector3:
    """Return `left + right` componentwise."""
    return (left[0] + right[0], left[1] + right[1], left[2] + right[2])


def vector_scale(vector: Vector3, factor: float) -> Vector3:
    """Return `vector * factor` componentwise."""
    return (vector[0] * factor, vector[1] * factor, vector[2] * factor)


def vector_magnitude(vector: Vector3) -> float:
    """Return the Euclidean magnitude of a 3-vector."""
    return math.sqrt(vector[0] ** 2 + vector[1] ** 2 + vector[2] ** 2)


def determinant(matrix: Matrix3) -> float:
    """Return the determinant of a 3x3 matrix.

    Args:
        matrix: A 3x3 row-major matrix.

    Returns:
        (float) The determinant. For a proper rotation this is `+1`; a value near
        zero marks a collapsed, non-invertible frame.
    """
    (a, b, c), (d, e, f), (g, h, i) = matrix
    return a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)


def is_finite_pose(pose: EEPose) -> bool:
    """Report whether every element of a pose is finite.

    Args:
        pose: The pose under check.

    Returns:
        (bool) True when no rotation or translation element is NaN or infinite.
    """
    for row in pose.rotation:
        if not all(math.isfinite(value) for value in row):
            return False
    return all(math.isfinite(value) for value in pose.translation)


def transpose(matrix: Matrix3) -> Matrix3:
    """Return the transpose of a 3x3 matrix."""
    (a, b, c), (d, e, f), (g, h, i) = matrix
    return ((a, d, g), (b, e, h), (c, f, i))


def matmul(left: Matrix3, right: Matrix3) -> Matrix3:
    """Return the product of two 3x3 matrices (`left · right`)."""
    # The nested comprehension yields a 3x3 tuple-of-tuples, the shape Matrix3 names.
    return tuple(  # type: ignore[return-value]
        tuple(sum(left[row][k] * right[k][col] for k in range(3)) for col in range(3))
        for row in range(3)
    )


def geodesic_angle(from_rotation: Matrix3, to_rotation: Matrix3) -> float:
    """Return the angle of the shortest rotation carrying one frame to the other.

    Args:
        from_rotation: The starting rotation.
        to_rotation: The target rotation.

    Returns:
        (float) The geodesic angle in radians, `[0, π]`.
    """
    relative = matmul(transpose(from_rotation), to_rotation)
    trace = relative[0][0] + relative[1][1] + relative[2][2]
    cos_theta = _clamp((trace - 1.0) / 2.0, -1.0, 1.0)
    return math.acos(cos_theta)


def clamp_rotation_toward(
    from_rotation: Matrix3, to_rotation: Matrix3, max_angle: float
) -> Matrix3:
    """Rotate from one frame toward another by at most `max_angle` radians.

    The clamp travels the same geodesic axis the full rotation would, so a limited
    angular step keeps the direction of the operator's motion and only bounds its
    size — the angular half of the EE velocity limit (`FR-TEL-037`).

    Args:
        from_rotation: The previous commanded rotation.
        to_rotation: The requested rotation.
        max_angle: The largest permitted angular step, radians (non-negative).

    Returns:
        (Matrix3) `to_rotation` when the step is within the limit, otherwise the
        rotation reached by turning `max_angle` along the geodesic to it.
    """
    relative = matmul(transpose(from_rotation), to_rotation)
    angle = geodesic_angle(from_rotation, to_rotation)
    if angle <= max_angle:
        return to_rotation
    axis = _rotation_axis(relative, angle)
    if axis is None:
        return to_rotation
    return matmul(from_rotation, _rodrigues(axis, max_angle))


def _rotation_axis(rotation: Matrix3, angle: float) -> Vector3 | None:
    """Extract the unit rotation axis of a rotation with a known angle.

    Args:
        rotation: The rotation matrix.
        angle: Its geodesic angle, radians.

    Returns:
        (Vector3 | None) The unit axis, or None when the axis is numerically
        undefined (angle near zero), in which case the caller leaves the pose alone.
    """
    sin_theta = math.sin(angle)
    if abs(sin_theta) < _AXIS_SINGULAR_EPS:
        return None
    (_, r01, r02), (r10, _, r12), (r20, r21, _) = rotation
    scale = 1.0 / (2.0 * sin_theta)
    return ((r21 - r12) * scale, (r02 - r20) * scale, (r10 - r01) * scale)


def _rodrigues(axis: Vector3, angle: float) -> Matrix3:
    """Build the rotation of `angle` radians about a unit `axis` (Rodrigues form)."""
    x, y, z = axis
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    one_minus = 1.0 - cos_a
    return (
        (
            cos_a + x * x * one_minus,
            x * y * one_minus - z * sin_a,
            x * z * one_minus + y * sin_a,
        ),
        (
            y * x * one_minus + z * sin_a,
            cos_a + y * y * one_minus,
            y * z * one_minus - x * sin_a,
        ),
        (
            z * x * one_minus - y * sin_a,
            z * y * one_minus + x * sin_a,
            cos_a + z * z * one_minus,
        ),
    )


def _clamp(value: float, low: float, high: float) -> float:
    """Clamp a scalar to `[low, high]`."""
    if value < low:
        return low
    if value > high:
        return high
    return value
