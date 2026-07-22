"""Domain constants for the WP-2B-03 v2 gravity-model verification (FR-SAF-072, spec 12 §2.6).

The joint layout is inherited from WP-2B-01 (`ARM_JOINT_COUNT`, `JOINT2_INDEX`) so this package
never redefines where joint2 sits or how wide an arm vector is. The wrist joints and the
anomaly thresholds are the two verification-specific facts this WP owns: which joints the
relocated link7 mass loads, and how large a joint-2 residual has to be before it reads as the
+pi/2-shift fingerprint rather than ordinary model error.
"""

from __future__ import annotations

from backend.dynamics.constants import ARM_JOINT_COUNT, JOINT2_INDEX

__all__ = [
    "ARM_JOINT_COUNT",
    "JOINT2_INDEX",
    "J2_ANOMALY_ABS_FLOOR_NM",
    "J2_ANOMALY_RATIO",
    "REAL_MEASUREMENT_BASIS",
    "SYNTHETIC_BASIS",
    "WRIST_DOMINANCE_FRACTION",
    "WRIST_JOINT_INDICES",
]

# The three wrist joints (joint5, joint6, joint7), zero-based, whose gravity term is loaded by
# the mass distal to the wrist. In v2 that mass is the end-effector subtree — the place the v1
# link7 mass was moved to (spec 12 §2.6, FR-SAF-033) — so these are the joints the link7->EE
# transfer impact is quantified on.
WRIST_JOINT_INDICES = (4, 5, 6)

# Joint2 residual-anomaly thresholds (acceptance ②, the +pi/2-shift fingerprint). A model in
# the correct v2 convention keeps the shoulder residual comparable to its peers; an un-shifted
# model swaps sin<->cos at joint2 and its residual dominates. A residual is flagged as the
# fingerprint only when BOTH hold, so ordinary sub-Nm scatter never trips it:
#   * joint2's residual exceeds the median of the other joints by this ratio, and
#   * joint2's residual is above an absolute floor (below it, a large ratio is measurement
#     noise, not a shoulder-gravity sign error).
J2_ANOMALY_RATIO = 3.0
J2_ANOMALY_ABS_FLOOR_NM = 0.5

# A wrist joint's residual is "dominated" by the relocated EE mass when the EE-subtree gravity
# contribution accounts for at least this fraction of that joint's modelled gravity. Above it,
# a wrist residual is attributable to EE mass/CoM error and belongs in the payload model
# (WP-2B-04), which is the WP-2B-03 negative branch for the wrist.
WRIST_DOMINANCE_FRACTION = 0.5

# Measurement bases, recorded on every artifact so an offline machinery run can never read as a
# real verdict. Mirrors the WP-2A-06 stopbench convention: SYNTHETIC exercises the residual and
# anomaly math on this host; REAL is a torque-ON pose-grid capture supplied through the fixture
# hook. A SYNTHETIC-basis run is always provisional and is never a PG-FRIC-001 preceding pass.
SYNTHETIC_BASIS = "synthetic-measurements"
REAL_MEASUREMENT_BASIS = "real-pose-grid"
