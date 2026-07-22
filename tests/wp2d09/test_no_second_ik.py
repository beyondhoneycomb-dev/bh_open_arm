"""No second IK: the gate reaches Kinematics only through the reused sim.ik builder.

WP-2D-09 reuses WP-2D-01's Cartesian jog for the IK-existence check; it must not stand
up a second solver. Like WP-2D-01's own reuse test, the static half is an AST scan: no
file under ``backend/moveto`` references the banned ``Kinematics`` / ``_IKSolver``
symbols, so the gate cannot construct an IK off the ordered ``sim.ik`` path. This needs
no robot stack — it reads source — so it holds in the light lane too.
"""

from __future__ import annotations

from sim.ik.staticcheck import scan_tree
from tests.wp2d09 import MOVETO_PACKAGE_DIR


def test_moveto_tree_has_no_banned_solver_reference() -> None:
    # exempt_owner is False: backend/moveto is not the sim/ik owning tree, so it is
    # scanned in full. A single direct Kinematics/_IKSolver reference would fail here.
    assert scan_tree(MOVETO_PACKAGE_DIR, exempt_owner=False) == []
