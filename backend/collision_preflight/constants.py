"""Named constants for the collision preflight (WP-2C-08).

Every value here is a spec-given identifier, a provenance label, or a deferral marker —
never a measured pass line. The collision margin is not redeclared: the default and the
zero-margin policy are `WP-1-06`'s (`backend.safety_bringup`), imported at the point of
use so there is one margin canon, not two (`12` FR-SAF-011).

The four deployment targets are read from `targets.matrix.FLEET_TARGETS` for the same
reason — `00` §2.1 P-2 owns that set, and the per-target bench must render a verdict slot
for exactly those four (`03` §5.11), so re-typing them here would be a second truth.
"""

from __future__ import annotations

from targets.matrix import FLEET_TARGETS

# This work package and the gate whose collision-check latency budget it consumes. The
# preflight is IK-independent (`02b` WP-2C-08 contract): `mink.CollisionAvoidanceLimit`
# is unused in the IK path, so an IK solution carries no collision guarantee, and the
# latency component of PG-IK-001 (`03` §5.11 downstream consumer) is measured here.
WP_ID = "WP-2C-08"
PG_IK_001 = "PG-IK-001"

# A collision geom must be able to both emit and receive contacts, i.e. carry a non-zero
# contype AND a non-zero conaffinity. A geom with either bitmask zeroed is invisible to
# one side of every pair test — the silent way a self-collision check goes vacuous
# (`02b` WP-2C-08 negative branch → FAIL_BLOCKING).
COLLISION_GEOM_NAME_TOKEN = "collision"
ARM_LEFT_NAME_TOKEN = "_left_"
ARM_RIGHT_NAME_TOKEN = "_right_"

# A reproducible in-range configuration that puts the two arms in self-collision, used to
# prove at startup that arm-arm contact is actually computed (`02b` WP-2C-08 ③). It is the
# first seed-0 in-range sample of the committed asset for which a left-arm geom contacts a
# right-arm geom (left link5/6/ee reaching across onto the right base): a positive control
# whose zero-contact result means the collision engine is silently disabled → FAIL_BLOCKING.
# Derived from the SHA-frozen `WP-0C-03` MJCF; an asset change SUPERSEDES it (re-derive).
KNOWN_ARM_ARM_COLLISION_LEFT: tuple[float, ...] = (
    -0.050314,
    0.094362,
    1.341162,
    2.264730,
    -0.281584,
    0.056108,
    -1.359729,
)
KNOWN_ARM_ARM_COLLISION_RIGHT: tuple[float, ...] = (
    -0.272097,
    1.055378,
    -0.787296,
    1.140767,
    1.342449,
    -0.423622,
    -1.314607,
)

# The four fleet deployment targets the per-target latency bench renders a slot for
# (`03` §5.11 target matrix; `00` §2.1 P-2 is the owning canon, imported not re-typed).
BENCH_TARGETS: tuple[str, ...] = FLEET_TARGETS

# The bench basis labels. The offline run exercises the real mj_forward machinery on THIS
# x86 host, so its latency numbers are real — but `NFR-TEL-004` forbids using an x86
# desktop figure as a target verdict, so every one of the four targets stays DEFERRED and
# the host number is recorded reference-only. The real per-target numbers arrive through
# the re-verification hook, tagged with the on-target basis, judged by identical machinery.
HOST_REFERENCE_BASIS = "host-x86-reference"
ON_TARGET_BASIS = "on-target-capture"

# The per-target verdict slot state before a real on-target capture exists. Never "PASS":
# a target with no on-target measurement has no verdict (`03` §5.11 renders per target).
TARGET_STATUS_DEFERRED = "DEFERRED"

# The environment variable pointing the deferred per-target re-verification hook at a
# directory of real on-target preflight-latency captures (one JSON per target). Until it
# is set, the per-target latency verdicts are DEFERRED and never asserted (THE ONE RULE).
FIXTURE_ENV_VAR = "OPENARM_COLLISION_PREFLIGHT_REAL_FIXTURE"

# Latency percentiles the bench and the re-verification hook report, by nearest-rank.
LATENCY_PERCENTILES: tuple[float, ...] = (50.0, 95.0, 99.0)
