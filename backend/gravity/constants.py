"""Domain constants for the WP-2B-02 gravity/Coriolis backend.

The committed v2 bimanual MJCF is the single inertial source: FR-SAF-034 fixes the default
`MUJOCO_V2` backend as the one that computes gravity from v2 inertia, and that inertia lives
in this asset. The joint names index the v2 joint convention WP-2B-01 defines and this package
verifies at load — feeding a v1 pose here without WP-2B-01's +pi/2 joint2 shift puts a
sin<->cos error into the shoulder gravity term (spec 12 §2.6), so the convention is not a
detail the backend may assume.
"""

from __future__ import annotations

from pathlib import Path

from backend.dynamics.constants import ARM_JOINT_COUNT

# Repository-root-relative path to the committed v2 model, resolved from this file so the
# backend loads the same asset regardless of the caller's working directory. Read-only:
# `sim/mjcf` is owned by Wave 0/1 and this package never writes it.
_REPO_ROOT = Path(__file__).resolve().parents[2]
MJCF_V2_PATH = _REPO_ROOT / "sim" / "mjcf" / "v2" / "openarm_bimanual.xml"

# gravity_scale runtime bounds (spec 12 §2.6 config `comp.dynamics_backend` family / FR-SAF-034):
# a payload/gravity trim, default 1.0 = full modelled gravity. A value outside the band is a
# misconfiguration and is refused at set time, not silently clamped.
GRAVITY_SCALE_MIN = 0.0
GRAVITY_SCALE_MAX = 1.2
GRAVITY_SCALE_DEFAULT = 1.0


def _arm_joint_names(side: str) -> tuple[str, ...]:
    """Return one arm's joint1..joint7 mujoco joint names for `side` ("right"/"left")."""
    return tuple(f"openarm_{side}_joint{index}" for index in range(1, ARM_JOINT_COUNT + 1))


# The seven actuated joints of each follower arm, in joint1..joint7 order. The gripper is not
# an arm joint and carries no gravity term here (v2 defines no finger dynamics — spec 12 §2.6).
RIGHT_ARM_JOINT_NAMES = _arm_joint_names("right")
LEFT_ARM_JOINT_NAMES = _arm_joint_names("left")

# Absolute tolerance for the joint2 range cross-check against WP-2B-01's V2_JOINT2_RANGE_RAD.
# The spec writes the v2 endpoints to five places (-0.17453, 3.3161); 1e-4 rad admits that
# rounding while still rejecting a v1-convention model (whose joint2 range differs by ~pi/2).
V2_RANGE_ABS_TOL_RAD = 1.0e-4
