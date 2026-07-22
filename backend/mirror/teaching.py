"""Mirror a whole teaching point (WP-2D-08 consuming the WP-2D-05 schema).

WP-2D-05 owns the ``TeachingPoint`` record; this module does not redefine it. It replaces
exactly three fields — arm side, joint vector, EE pose — and carries every other field
(the ``zero_method`` / ``zeroed_at`` provenance the WP-2D-05 replay gate checks, the
shared lifter height, the name and gains) verbatim through ``dataclasses.replace``, so the
mirrored point is re-validated by the same schema that made the original.

``ee_pose`` is reflected, not recomputed by FK: the source pose is captured ground truth,
and ``reflect_ee_pose`` equals the FK of the mirrored joints to floating point
(test_fk_equality), so the reflected pose stays consistent with the mirrored ``q_urdf``
while preserving what was taught.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np

from backend.mirror.convention import mirror_arm_side, mirror_q_urdf, reflect_ee_pose
from backend.teaching import TeachingPoint


def mirror_teaching_point(point: TeachingPoint) -> TeachingPoint:
    """Return the opposite-arm mirror of a teaching point.

    The arm side flips, ``q_urdf`` mirrors by the FR-MAN-046 convention, and ``ee_pose``
    reflects across the sagittal plane; all other fields are carried unchanged. The
    transform is an exact involution: mirroring a mirrored point restores the original.

    Args:
        point: The WP-2D-05 teaching point to mirror.

    Returns:
        (TeachingPoint) A new, schema-validated point for the opposite arm.
    """
    return replace(
        point,
        arm_side=mirror_arm_side(point.arm_side),
        q_urdf=mirror_q_urdf(np.asarray(point.q_urdf, dtype=float)).tolist(),
        ee_pose=reflect_ee_pose(np.asarray(point.ee_pose, dtype=float)).tolist(),
    )
