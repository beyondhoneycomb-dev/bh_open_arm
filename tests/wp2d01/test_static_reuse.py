"""Acceptance ① — the jog reuses the ordered IK build; it never reaches a raw Kinematics.

Two halves, mirroring WP-0C-02. Statically, no file under ``backend/cartesian_jog``
references the banned ``Kinematics`` / ``_IKSolver`` symbols — the jog cannot construct
an IK off the ordered path. At runtime, the reused ``sim.ik`` order enforcement still
bites: a Kinematics built before the jnt_range override is rejected, which is the
"Kinematics without override => build fails" the acceptance names. The jog is proven to
reuse the Wave 0-C adapter by identity, not to reimplement a second IK.
"""

from __future__ import annotations

import pytest

from sim.ik.staticcheck import scan_tree
from tests.wp2d01 import JOG_PACKAGE_DIR


def test_jog_tree_has_no_banned_solver_reference() -> None:
    # exempt_owner is False: cartesian_jog is not the sim/ik owning tree, so it is
    # scanned in full. A single direct Kinematics/_IKSolver reference would fail here.
    assert scan_tree(JOG_PACKAGE_DIR, exempt_owner=False) == []


def test_build_reaches_ik_only_through_the_ordered_builder() -> None:
    pytest.importorskip("mujoco")
    pytest.importorskip("mink")
    pytest.importorskip("lerobot")

    import backend.cartesian_jog.jog as jog_module
    from sim.ik.adapter import IkAdapter, build_ik_adapter

    # The jog module's only door to a Kinematics is sim.ik's ordered builder.
    assert jog_module.build_ik_adapter is build_ik_adapter

    from backend.cartesian_jog import build_cartesian_jog

    jog = build_cartesian_jog()
    # The IK the jog drives is a sim.ik adapter instance, not a bespoke solver.
    assert isinstance(jog._adapter, IkAdapter)


def test_kinematics_before_override_is_rejected_by_the_reused_builder() -> None:
    pytest.importorskip("mujoco")
    pytest.importorskip("mink")
    pytest.importorskip("lerobot")

    from openarm_control.config import ArmSetup
    from openarm_control.kinematics import IKParams

    from sim.ik.asset import (
        EE_FRAME_TYPE,
        HOME_KEYFRAME,
        LEFT_EE_SITE,
        RIGHT_EE_SITE,
        fixed_cell_xml,
    )
    from sim.ik.override import IkOrderError, OrderedIkBuild

    setup = ArmSetup.from_args(
        xml=str(fixed_cell_xml()),
        mode="bimanual",
        frame_right=RIGHT_EE_SITE,
        frame_type_right=EE_FRAME_TYPE,
        frame_left=LEFT_EE_SITE,
        frame_type_left=EE_FRAME_TYPE,
        keyframe=HOME_KEYFRAME,
    )
    build = OrderedIkBuild(setup)
    with pytest.raises(IkOrderError, match="before the jnt_range override"):
        build.build_kinematics(IKParams())
