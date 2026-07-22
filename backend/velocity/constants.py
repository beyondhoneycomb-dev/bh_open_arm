"""Named constants for the bootstrap velocity limiter (WP-2A-04).

Every value here is a spec-given identifier, an asset-derived physical fact, or a
policy constant fixed by the plan — never a measured pass line. The velocity
magnitudes the limiter enforces are NOT declared here: they are imported from the
WP-1-06 derivation (`backend.safety_bringup.velocity.bootstrap_limiter_rad_s`),
which is the single source of truth for the physical canon. This module holds only
the runtime policy (default global scale, ramp-down band) and the mechanical
provenance (gear ratios) the derivation-basis artifact must attach.
"""

from __future__ import annotations

from backend.can.rid.motor_limits import MotorType

# The default global velocity scale (`02b` §1.2 acceptance ④ / `03` §5.6.0 ②). The
# limiter opens at ten percent of the derived ceiling and a caller may widen it up to
# one hundred percent; it may never exceed it, because a scale above unity would let a
# command past the derived active limit the scale exists to sit under.
DEFAULT_GLOBAL_SCALE = 0.10
MIN_GLOBAL_SCALE = 0.0
MAX_GLOBAL_SCALE = 1.0

# The near-limit ramp-down band, degrees (`02b` §1.2 acceptance ⑤). Within this many
# degrees of an operational position limit, the velocity ceiling toward that limit is
# ramped linearly to zero, so a joint decelerates into its bound rather than striking it
# at the scaled ceiling. Motion away from the bound is never ramped.
RAMP_DOWN_BAND_DEG = 5.0

# The version stamped on the bootstrap limit set. A refinement (`PG-VEL-001`-verified)
# replaces it only with a strictly greater version (acceptance ⑥), so the version is the
# monotonic identity that makes "which set is active" answerable and a stale set nameable.
BOOTSTRAP_LIMIT_SET_VERSION = 1

# The provenance label distinguishing the arithmetic bootstrap set from a later refined
# set. It is recorded on the artifact so a reader can tell a derived-conservative ceiling
# from a rig-verified one without inspecting the basis URIs.
PROVENANCE_BOOTSTRAP = "bootstrap"
PROVENANCE_REFINED = "refined"

# Per-motor gear reduction ratio (`03` §2.2 motor table: DM4310 10:1 / DM4340 40:1 /
# DM8009 9:1; cross-checked at `02` §2.1). The register V_MAX (RID 22) the derivation
# reads is the OUTPUT-shaft velocity ceiling — the reduction is already embodied in it
# (`03` trap 2 compares register 8 rad/s directly against the output-side catalogue and
# URDF figures). The ratio is therefore attached as the mechanical basis that makes the
# register an output-side quantity, not re-applied to the value; re-dividing would
# double-count the reduction. It is a required field of the derivation artifact
# (acceptance ②), so its absence load-refuses a limit rather than passing silently.
GEAR_RATIO_BY_MOTOR: dict[MotorType, float] = {
    MotorType.DM8009: 9.0,
    MotorType.DM4340: 40.0,
    MotorType.DM4310: 10.0,
}

# The physical sources the bootstrap derivation rests on — datasheet register V_MAX, the
# motor catalogue no-load speed, and the URDF velocity limit. Each is cited by the repo's
# canonical document-number reference (`03` §2.2 register/gear, `03` §5.6.0 ① derivation),
# the same form used throughout the corpus, so the anchor resolves without embedding a
# document's display filename. None of these is a rig measurement, which is what keeps the
# bootstrap set clear of the self-approval `assert_derivation_basis_not_self` forbids: a
# derived limit may never cite the sweep it is meant to authorise.
BOOTSTRAP_BASIS_URIS: tuple[str, ...] = (
    "spec/03#2.2/motor-register-vmax-and-gear-ratio",
    "asset/openarm_v2.0/config/arm/joint/joint_limits.yaml#velocity",
    "spec/03#trap-2/catalogue-no-load-speed",
)
