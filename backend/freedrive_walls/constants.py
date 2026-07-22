"""Named parameters of the Freedrive virtual-wall repulsion and detection switch (WP-2D-04).

Every literal the repulsion ramp depends on is named here, so the one place a value is
decided is the one place it is read (`14` §2, constants rule). The per-joint physical
envelope is not restated: the URDF effort limit and the arm joint count come from
`backend.safety_bringup.constants` (the canonical `03` §2.1 table), so this module adds only
the band width and the effort-headroom fractions the wall itself introduces.
"""

from __future__ import annotations

from backend.safety_bringup.constants import ARM_JOINT_COUNT, URDF_EFFORT_LIMIT_NM
from contracts.units.conversions import deg_to_rad
from contracts.units.tags import Deg

# The near-limit band, radians. `04` FR-MAN-036: the wall engages within 5 deg of a joint
# limit. Carried through the one sanctioned CTR-UNIT crossing rather than a bare
# `math.radians`, so the band lives in the same unit discipline as the limits.
NEAR_LIMIT_BAND_DEG = 5.0
NEAR_LIMIT_BAND_RAD = deg_to_rad(Deg(NEAR_LIMIT_BAND_DEG)).value

# The default share of a joint's URDF effort the wall may spend at the hardstop. `04`
# FR-MAN-036 caps the repulsion within the effort limit; the default leaves headroom so the
# wall firmly resists a hand-guide without saturating the actuator against the gravity and
# friction compensation already on the tau channel. A fraction of exactly 1.0 spends the
# whole effort; above 1.0 is refused — that is the repulsion-exceeds-effort FAIL_BLOCKING
# branch (`02b` §4.2 WP-2D-04), enforced in `repulsion.JointWall`.
DEFAULT_REPULSION_EFFORT_FRACTION = 0.5
MAX_REPULSION_EFFORT_FRACTION = 1.0

__all__ = [
    "ARM_JOINT_COUNT",
    "DEFAULT_REPULSION_EFFORT_FRACTION",
    "MAX_REPULSION_EFFORT_FRACTION",
    "NEAR_LIMIT_BAND_DEG",
    "NEAR_LIMIT_BAND_RAD",
    "URDF_EFFORT_LIMIT_NM",
]
