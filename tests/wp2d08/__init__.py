"""WP-2D-08 acceptance suite — mirror teaching (FR-MAN-046 / FR-MAN-017).

Shared paths and a right-arm sample point. The convention core is pure numpy, but the
FK cross-check and the pinned limits reach the sim stack (mujoco / mink / openarm_control)
and LeRobot, which are the optional ``[robot]`` group, so the modules that need them
``importorskip`` first. The WP-2D-05 ``TeachingPoint`` schema is light and imported here.
"""

from __future__ import annotations

from pathlib import Path

from backend.teaching import TeachingPoint

REPO_ROOT = Path(__file__).resolve().parents[2]
MIRROR_PACKAGE_DIR = REPO_ROOT / "backend" / "mirror"


def right_sample_point() -> TeachingPoint:
    """Return a representative right-arm teaching point for mirror tests.

    The gripper is at its right open bound (-0.7854) so the mirror's sign flip lands at
    the left open bound, and joint4 (index 3) is off zero so a same-sign vs flipped-sign
    mistake is observable.
    """
    return TeachingPoint(
        name="grasp_A",
        arm_side="right",
        q_urdf=[0.1, -0.2, 0.3, 1.2, -0.4, 0.5, -0.6, -0.7854],
        ee_pose=[0.41, -0.25, 1.12, 0.75, -0.30, -0.58, -0.06],
        gain_profile="teach_soft",
        zero_method="mechanical_jig",
        zeroed_at="2026-07-22T00:00:00Z",
        q_lift=0.12,
        timestamp="2026-07-22T00:00:01Z",
    )


__all__ = ["MIRROR_PACKAGE_DIR", "REPO_ROOT", "right_sample_point"]
