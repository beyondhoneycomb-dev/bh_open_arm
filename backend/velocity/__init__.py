"""WP-2A-04 — the bootstrap velocity limiter that stands before the sweep.

The limiter is the dt-based, global-scale velocity limiter (`02b` §1.2 / `03` §5.6.0) that
`WP-2A-04` stands up first, before `PG-VEL-001` ever runs. It does not derive its own
velocity magnitudes — those are the WP-1-06 physical canon
(`backend.safety_bringup.velocity.bootstrap_limiter_rad_s`), imported so there is one source
of truth — and it does not reject commands the way the gateway velocity check does. It
SCALES and ramps a commanded velocity to a bounded one, refuses torque-ON when no limit set
is loaded, and replaces the bootstrap set only through an explicit, versioned, non-measured
refinement.

  * `derivation` — the per-joint limit set wrapped with its derivation basis (formula, gear
    ratio, motor V_MAX, winning source); a value with no basis is load-refused.
  * `limiter` — the runtime: global scale (default ≤10%), near-limit ramp-down, the arming
    guard, and the refinement path.

The two hardware-adjacent facts this band never fakes stay in WP-1-06: the command-following
sweep (`PG-VEL-001`) is a later verifier, deferred to a real fixture, not an input here.
"""

from __future__ import annotations

from backend.velocity.constants import (
    BOOTSTRAP_BASIS_URIS,
    BOOTSTRAP_LIMIT_SET_VERSION,
    DEFAULT_GLOBAL_SCALE,
    GEAR_RATIO_BY_MOTOR,
    MAX_GLOBAL_SCALE,
    MIN_GLOBAL_SCALE,
    PROVENANCE_BOOTSTRAP,
    PROVENANCE_REFINED,
    RAMP_DOWN_BAND_DEG,
)
from backend.velocity.derivation import (
    SOURCE_VELOCITY_CAP,
    DerivationBasisError,
    DerivedLimit,
    LimitSet,
    bootstrap_limit_set,
)
from backend.velocity.limiter import (
    LimiterNotArmedError,
    LimitResult,
    RefinementApproval,
    RefinementRefusedError,
    ScaleOutOfRangeError,
    StepResult,
    VelocityLimiter,
    bootstrap_velocity_limiter,
    ramp_bounds_from_safety_limits,
)

__all__ = [
    "BOOTSTRAP_BASIS_URIS",
    "BOOTSTRAP_LIMIT_SET_VERSION",
    "DEFAULT_GLOBAL_SCALE",
    "GEAR_RATIO_BY_MOTOR",
    "MAX_GLOBAL_SCALE",
    "MIN_GLOBAL_SCALE",
    "PROVENANCE_BOOTSTRAP",
    "PROVENANCE_REFINED",
    "RAMP_DOWN_BAND_DEG",
    "SOURCE_VELOCITY_CAP",
    "DerivationBasisError",
    "DerivedLimit",
    "LimitResult",
    "LimitSet",
    "LimiterNotArmedError",
    "RefinementApproval",
    "RefinementRefusedError",
    "ScaleOutOfRangeError",
    "StepResult",
    "VelocityLimiter",
    "bootstrap_limit_set",
    "bootstrap_velocity_limiter",
    "ramp_bounds_from_safety_limits",
]
