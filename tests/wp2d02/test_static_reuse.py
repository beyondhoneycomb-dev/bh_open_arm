"""No second IK: the singularity tree references no banned solver symbol.

WP-2D-02 reuses the WP-2D-01 jog (which itself reuses the Wave 0-C ``sim.ik`` adapter)
rather than constructing its own solver. The elbow swivel re-fixes the EE through the
jog's ``plan_pose``; the monitor only reads a Jacobian. So the whole ``backend/singularity``
tree must be free of ``Kinematics`` / ``_IKSolver`` references, exactly as the jog tree is
— the same static guarantee, checked the same way (an AST scan, not a runtime path).
"""

from __future__ import annotations

from sim.ik.staticcheck import scan_tree
from tests.wp2d02 import SINGULARITY_PACKAGE_DIR


def test_singularity_tree_has_no_banned_solver_reference() -> None:
    # exempt_owner=False so nothing under the tree is skipped: a single direct
    # Kinematics/_IKSolver reference anywhere in backend/singularity would fail here.
    assert scan_tree(SINGULARITY_PACKAGE_DIR, exempt_owner=False) == []
