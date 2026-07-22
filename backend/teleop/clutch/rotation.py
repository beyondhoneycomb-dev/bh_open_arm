"""Quaternion helpers shared by the delta scaler and the pose smoother.

Both the independent rotation scale (`scale.py`, `FR-TEL-029`) and the SLERP arm of the
One Euro smoother (`smoother.py`, `FR-TEL-039`) need the same small set of rotation
operations, so they live here once rather than being duplicated on each path — a second
copy is how the two paths silently disagree on convention.

Convention: every quaternion is an `(x, y, z, w)` numpy array, matching the VR pose
fixture (`contracts/fixtures/vr_pose_stream.py`, `lt`/`rt` fields). Functions normalise
defensively and take the shortest arc, but pose sanity (a non-finite or degenerate
quaternion) is the safety gate's job (`WP-3B-10`), not this module's.
"""

from __future__ import annotations

import numpy as np

# The identity rotation in (x, y, z, w). `scale_rotation` interpolates away from it, so
# it is named rather than rebuilt at each call.
IDENTITY_QUAT = np.array([0.0, 0.0, 0.0, 1.0])

# Above this absolute dot product two quaternions are nearly parallel; SLERP's sine
# denominator underflows, so the interpolation falls back to normalised linear blend.
_SLERP_PARALLEL_DOT = 0.9995


def quat_normalize(quat: np.ndarray) -> np.ndarray:
    """Return the unit quaternion in the direction of `quat`.

    Args:
        quat: An `(x, y, z, w)` quaternion.

    Returns:
        (np.ndarray) The unit quaternion; the identity if `quat` has zero norm.
    """
    norm = float(np.linalg.norm(quat))
    if norm == 0.0:
        return IDENTITY_QUAT.copy()
    return np.asarray(quat, dtype=float) / norm


def quat_conjugate(quat: np.ndarray) -> np.ndarray:
    """Return the conjugate (inverse rotation for a unit quaternion).

    Args:
        quat: An `(x, y, z, w)` quaternion.

    Returns:
        (np.ndarray) The conjugate `(-x, -y, -z, w)`.
    """
    return np.array([-quat[0], -quat[1], -quat[2], quat[3]])


def quat_multiply(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    """Compose two rotations: the result applies `right` first, then `left`.

    Args:
        left: The outer rotation, `(x, y, z, w)`.
        right: The inner rotation, `(x, y, z, w)`.

    Returns:
        (np.ndarray) The Hamilton product `left ⊗ right`, `(x, y, z, w)`.
    """
    lx, ly, lz, lw = left
    rx, ry, rz, rw = right
    return np.array(
        [
            lw * rx + lx * rw + ly * rz - lz * ry,
            lw * ry - lx * rz + ly * rw + lz * rx,
            lw * rz + lx * ry - ly * rx + lz * rw,
            lw * rw - lx * rx - ly * ry - lz * rz,
        ]
    )


def quat_angle(quat: np.ndarray) -> float:
    """Return the rotation magnitude of `quat` in radians, in `[0, pi]`.

    Args:
        quat: An `(x, y, z, w)` quaternion.

    Returns:
        (float) The unsigned rotation angle.
    """
    unit = quat_normalize(quat)
    return float(2.0 * np.arccos(np.clip(abs(unit[3]), -1.0, 1.0)))


def angle_between(first: np.ndarray, second: np.ndarray) -> float:
    """Return the shortest rotation angle (radians) between two orientations.

    Args:
        first: An `(x, y, z, w)` quaternion.
        second: An `(x, y, z, w)` quaternion.

    Returns:
        (float) The unsigned relative angle, in `[0, pi]`.
    """
    dot = float(np.dot(quat_normalize(first), quat_normalize(second)))
    return float(2.0 * np.arccos(np.clip(abs(dot), -1.0, 1.0)))


def slerp(start: np.ndarray, end: np.ndarray, fraction: float) -> np.ndarray:
    """Spherically interpolate from `start` to `end` along the shortest arc.

    Args:
        start: The `fraction = 0` orientation, `(x, y, z, w)`.
        end: The `fraction = 1` orientation, `(x, y, z, w)`.
        fraction: Interpolation parameter, typically in `[0, 1]`.

    Returns:
        (np.ndarray) The interpolated unit quaternion.
    """
    q_start = quat_normalize(start)
    q_end = quat_normalize(end)
    dot = float(np.dot(q_start, q_end))
    # Take the shortest path: a quaternion and its negation are the same rotation.
    if dot < 0.0:
        q_end = -q_end
        dot = -dot
    if dot > _SLERP_PARALLEL_DOT:
        return quat_normalize(q_start + fraction * (q_end - q_start))
    theta_0 = float(np.arccos(dot))
    sin_theta_0 = float(np.sin(theta_0))
    theta = theta_0 * fraction
    scale_start = float(np.sin(theta_0 - theta) / sin_theta_0)
    scale_end = float(np.sin(theta) / sin_theta_0)
    return scale_start * q_start + scale_end * q_end


def scale_rotation(quat: np.ndarray, scale: float) -> np.ndarray:
    """Scale a rotation's angle about its own axis, keeping the axis fixed.

    Interpolating from the identity by `scale` shrinks (or grows) the rotation angle
    while preserving the axis — the independent rotation-scale operation joint6's narrow
    ±45° limit requires (`FR-TEL-029`). `scale = 1.0` returns `quat` unchanged; `0.0`
    returns the identity.

    Args:
        quat: The rotation to scale, `(x, y, z, w)`.
        scale: The angle multiplier.

    Returns:
        (np.ndarray) The scaled rotation, `(x, y, z, w)`.
    """
    return slerp(IDENTITY_QUAT, quat, scale)
