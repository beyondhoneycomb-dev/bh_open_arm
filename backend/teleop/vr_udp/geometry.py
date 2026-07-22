"""Small, exact rotation/quaternion primitives for the VR coordinate chain.

Pure stdlib arithmetic on plain float tuples: a 3x3 matrix-vector product, a
scalar-first Hamilton product, the Unity left-handed to right-handed axis
conversion, and a quaternion-to-matrix map used only to prove `Q_ROBOT` and
`R_ROBOT` are the same rotation (`transform` and its test). Kept dependency-free
so the whole VR-source path stays in the AI-offline light lane and every value is
bit-reproducible rather than subject to a BLAS backend.

Quaternion convention here is scalar-first `(w, x, y, z)`. The UDP wire quaternion
is scalar-last `(x, y, z, w)` (`contracts/fixtures/vr_pose_stream.py`), so the wire
order is converted at exactly one boundary — `unity_lh_to_rh_quaternion`.
"""

from __future__ import annotations

Vec3 = tuple[float, float, float]
Mat3 = tuple[Vec3, Vec3, Vec3]
# Scalar-first quaternion `(w, x, y, z)`.
Quat = tuple[float, float, float, float]


def rotate_vector(matrix: Mat3, vector: Vec3) -> Vec3:
    """Apply a 3x3 rotation matrix to a 3-vector.

    Args:
        matrix: Row-major 3x3 rotation.
        vector: The vector to rotate.

    Returns:
        (Vec3) `matrix @ vector`.
    """
    return (
        matrix[0][0] * vector[0] + matrix[0][1] * vector[1] + matrix[0][2] * vector[2],
        matrix[1][0] * vector[0] + matrix[1][1] * vector[1] + matrix[1][2] * vector[2],
        matrix[2][0] * vector[0] + matrix[2][1] * vector[1] + matrix[2][2] * vector[2],
    )


def subtract(left: Vec3, right: Vec3) -> Vec3:
    """Return the component-wise difference `left - right`."""
    return (left[0] - right[0], left[1] - right[1], left[2] - right[2])


def add(left: Vec3, right: Vec3) -> Vec3:
    """Return the component-wise sum `left + right`."""
    return (left[0] + right[0], left[1] + right[1], left[2] + right[2])


def quat_multiply(left: Quat, right: Quat) -> Quat:
    """Hamilton product of two scalar-first quaternions.

    Composition order is the matrix order: `quat_multiply(a, b)` is the rotation
    that applies `b` then `a`, so it equals `mat_of(a) @ mat_of(b)`.

    Args:
        left: Scalar-first `(w, x, y, z)`.
        right: Scalar-first `(w, x, y, z)`.

    Returns:
        (Quat) The scalar-first product.
    """
    aw, ax, ay, az = left
    bw, bx, by, bz = right
    return (
        aw * bw - ax * bx - ay * by - az * bz,
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
    )


def unity_lh_to_rh_position(position: Vec3) -> Vec3:
    """Convert a Unity left-handed position to the right-handed OpenXR frame.

    The upstream protocol negates Z: `p = [x, y, -z]` (`05` §2.7).

    Args:
        position: Unity `(x, y, z)`.

    Returns:
        (Vec3) Right-handed `(x, y, -z)`.
    """
    return (position[0], position[1], -position[2])


def unity_lh_to_rh_quaternion(quaternion_xyzw: tuple[float, float, float, float]) -> Quat:
    """Convert a Unity left-handed wire quaternion to a right-handed scalar-first one.

    The wire quaternion is scalar-last `(x, y, z, w)`; the upstream conversion is
    `q = [w, -x, -y, z]` (`05` §2.7), which also re-orders it to scalar-first. This
    is the one place the wire's scalar-last order is read.

    Args:
        quaternion_xyzw: Wire quaternion `(x, y, z, w)`.

    Returns:
        (Quat) Right-handed scalar-first `(w, -x, -y, z)`.
    """
    qx, qy, qz, qw = quaternion_xyzw
    return (qw, -qx, -qy, qz)


def quat_to_mat3(quaternion: Quat) -> Mat3:
    """Convert a unit scalar-first quaternion to its rotation matrix.

    Used to prove that the precomputed `Q_ROBOT` constant is the same rotation as
    the `R_ROBOT` matrix (they are two spellings of one frame change, and a test
    must be able to reject a drift between them).

    Args:
        quaternion: A unit scalar-first quaternion.

    Returns:
        (Mat3) The equivalent row-major rotation matrix.
    """
    w, x, y, z = quaternion
    return (
        (1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - w * z), 2.0 * (x * z + w * y)),
        (2.0 * (x * y + w * z), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - w * x)),
        (2.0 * (x * z - w * y), 2.0 * (y * z + w * x), 1.0 - 2.0 * (x * x + y * y)),
    )


def is_finite_vec(vector: tuple[float, ...]) -> bool:
    """Report whether every component of a vector is a finite real number.

    A NaN/inf on the wire is a corrupt datagram, not a pose; the parser rejects it
    rather than letting it reach a downstream solver. (Full pose-sanity — the
    `det ~ 0` singular-frame discard — is the WP-3B-10 safety gate, not this layer.)

    Args:
        vector: Any tuple of floats.

    Returns:
        (bool) True when all components are finite.
    """
    return all(x == x and x not in (float("inf"), float("-inf")) for x in vector)
