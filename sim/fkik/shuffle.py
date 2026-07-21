"""A qpos-order-permuted twin of the fixed cell, to prove name-based resolution.

`09` claims the kinematics resolves indices *at runtime by joint name*
(``mujoco.mj_name2id`` -> ``jnt_qposadr`` / ``jnt_dofadr``), and is therefore
"robust to changes in MJCF qpos ordering". A claim about an absence — that no code
depends on the qpos *layout* — is only proven by changing that layout and showing
the answer does not move. This module builds that changed-layout model.

The permutation is a single hinge joint added to the lifter body ahead of the arm
subtrees. MuJoCo assigns qpos in kinematic-tree order, so the added joint takes the
slot right after the lifter and pushes every arm joint's qpos/dof index up by one:
``openarm_left_joint1`` moves from qpos 1 to qpos 2, and so on for all eighteen arm
slots. Every joint keeps its *name*, so name resolution recovers each joint at its
new index; only code that hard-coded an index would now read the wrong slot.

The added joint has a hinge at value 0, which is the identity rotation, so the lifter
link — and thus both arm subtrees hanging off it — occupies exactly the same world
pose as in the canonical model. FK evaluated by name on the same named joint values
is therefore byte-identical between the two models (``fk_by_name`` below is what the
test compares). This is a genuine layout change with zero kinematic effect, which is
precisely what isolates "did the code follow the name" from "did the pose change".
"""

from __future__ import annotations

from pathlib import Path

import mujoco
import numpy as np
from openarm_control.poses import read_ee_pose
from openarm_mujoco.v2 import JointResolver

import sim.mjcf
from sim.ik.asset import EE_FRAME_TYPE, LEFT_EE_SITE, RIGHT_EE_SITE

# The WP-0C-03 fixed cell scene, relative to the sim.mjcf package. Resolved through
# sim.mjcf directly (rather than an indirection) because this module loads that asset
# to build the qpos-permuted twin, so the dependency on WP-0C-03's MJCF is real.
_CELL_XML_RELATIVE = Path("v2") / "cell.xml"

# The extra joint whose presence reorders the qpos layout. Named so a test can find
# it, and given a hair-thin range so it is unmistakably an inert layout perturbation
# rather than a functional degree of freedom.
PROBE_JOINT_NAME = "qpos_shuffle_probe"
_PROBE_HINGE_HALF_RANGE_RAD = 1e-6

# The lifter body the arms attach under; the probe joint is added here so its qpos
# slot lands ahead of every arm slot in the kinematic-tree ordering.
LIFTER_BODY_NAME = "openarm_lifter_link"

_EE_SITE = {"right": RIGHT_EE_SITE, "left": LEFT_EE_SITE}


def _cell_xml() -> Path:
    """Return the WP-0C-03 fixed cell path, resolved via the sim.mjcf package."""
    path = Path(sim.mjcf.__file__).resolve().parent / _CELL_XML_RELATIVE
    if not path.is_file():
        raise FileNotFoundError(f"fixed IK cell asset not found: {path}")
    return path


def build_canonical_model() -> mujoco.MjModel:
    """Load the WP-0C-03 fixed cell in its authored qpos ordering."""
    return mujoco.MjModel.from_xml_path(str(_cell_xml()))


def build_shuffled_model() -> mujoco.MjModel:
    """Build a twin of the fixed cell with the arm qpos indices shifted by one.

    The twin adds ``PROBE_JOINT_NAME`` to the lifter body, which permutes the qpos
    layout while leaving every joint name and every world pose unchanged (see the
    module docstring). It is compiled through ``MjSpec`` so no MJCF file is written
    and the WP-0C-03 asset is never edited.

    Returns:
        (mujoco.MjModel) The recompiled, qpos-reordered model.
    """
    spec = mujoco.MjSpec.from_file(str(_cell_xml()))
    lifter = _find_body(spec.worldbody, LIFTER_BODY_NAME)
    lifter.add_joint(
        name=PROBE_JOINT_NAME,
        type=mujoco.mjtJoint.mjJNT_HINGE,
        axis=[0.0, 0.0, 1.0],
        range=[-_PROBE_HINGE_HALF_RANGE_RAD, _PROBE_HINGE_HALF_RANGE_RAD],
        limited=True,
    )
    return spec.compile()


def _find_body(root: mujoco._specs.MjsBody, name: str) -> mujoco._specs.MjsBody:
    """Return the descendant body with the given name, or raise if absent.

    Args:
        root: The spec body to search under (inclusive).
        name: The body name to find.

    Returns:
        (mujoco._specs.MjsBody) The matching body.

    Raises:
        ValueError: When no body of that name exists under ``root``.
    """
    if root.name == name:
        return root
    child = root.first_body()
    while child is not None:
        found = _find_body(child, name)
        if found is not None:
            return found
        child = root.next_body(child)
    raise ValueError(f"body {name!r} not found in spec")


def qpos_index_of(model: mujoco.MjModel, joint_name: str) -> int:
    """Return a joint's qpos address, resolved by name.

    Args:
        model: The compiled model.
        joint_name: Fully-qualified MJCF joint name.

    Returns:
        (int) The joint's ``jnt_qposadr``.

    Raises:
        ValueError: When the joint is absent.
    """
    jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, joint_name)
    if jid < 0:
        raise ValueError(f"joint {joint_name!r} not found in model")
    return int(model.jnt_qposadr[jid])


def fk_by_name(
    model: mujoco.MjModel, right: np.ndarray, left: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Forward-kinematics both EE poses using only name-resolved indices.

    Both the joint writes (through ``JointResolver``, which resolves every arm joint
    by name) and the EE-site reads (through ``mj_name2id``) are name-based, so this
    is FK with no dependence on the qpos layout. It is the function whose output must
    match between the canonical and shuffled models.

    Args:
        model: The compiled model (canonical or shuffled).
        right: Right-arm driver values, float[8] = joints[0:7] + gripper[7].
        left: Left-arm driver values, float[8].

    Returns:
        (tuple[np.ndarray, np.ndarray]) The (right, left) EE poses,
        float[7] = [px, py, pz, qw, qx, qy, qz] each.
    """
    resolver = JointResolver(model)
    data = mujoco.MjData(model)
    resolver.set_qpos(data.qpos, right, "right")
    resolver.set_qpos(data.qpos, left, "left")
    mujoco.mj_forward(model, data)
    return _read_ee(model, data, "right"), _read_ee(model, data, "left")


def _read_ee(model: mujoco.MjModel, data: mujoco.MjData, side: str) -> np.ndarray:
    """Read one arm's EE-site pose, resolving the site id by name."""
    site_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, _EE_SITE[side])
    if site_id < 0:
        raise ValueError(f"EE site {_EE_SITE[side]!r} not found in model")
    return read_ee_pose(data, site_id, EE_FRAME_TYPE)
