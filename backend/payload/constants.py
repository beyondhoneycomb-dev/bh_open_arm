"""Domain constants for the WP-2B-04 payload model (mass/CoG registry).

Two spec figures anchor this package. FR-SAF-036 fixes the registry range at 0-6.0 kg
*including the end-effector* (nominal 4.1 kg / peak 6.0 kg), so a registered mass outside
that band is a mis-registration and is refused rather than silently accepted — an accepted
mis-registration is the FAIL_BLOCKING case (a constant residual offset that reads as a
permanent false or missed collision). FR-MAN-038 requires a pre-Freedrive check that the
gravity-compensation torque stays within a safety multiple of the per-joint effort limit;
the effort limit (40/40/27/27/7/7/7 Nm) is not re-declared here — it is imported from the
single source in `backend.safety_bringup`.

The safety multiple has no spec-given number (FR-MAN-038 is `[신규구현]`), so it is chosen
here as a documented, tunable derating and its value is justified against measured physics
in `EFFORT_SATURATION_SAFETY_MULTIPLE` below.
"""

from __future__ import annotations

# Registry mass band, kg, end-effector included (FR-SAF-036 / FR-MAN-033). The peak is the
# hard ceiling; a request above it or below zero is a mis-registration and is refused. The
# nominal is the rated payload whose "hold at max extension for one minute" duty (FR-MAN-038
# note) the effort preflight must keep admissible.
PAYLOAD_MASS_MIN_KG = 0.0
PAYLOAD_MASS_MAX_KG = 6.0
PAYLOAD_MASS_NOMINAL_KG = 4.1

# Sanity ceiling on the payload centre-of-gravity offset from the end-effector mount, metres.
# This is a units/frame-error guard (millimetres entered as metres, a wrong-magnitude value),
# NOT a mechanical limit: a CoG more than half a metre from the wrist mount on a 6 kg-rated
# arm is a data-entry error, and letting it through would corrupt every gravity reflection.
PAYLOAD_COG_MAX_OFFSET_M = 0.5

# The FR-MAN-038 effort-saturation safety multiple. Freedrive entry is refused when
# `EFFORT_SATURATION_SAFETY_MULTIPLE * |tau_grav_with_payload[j]| > effort_limit[j]` for any
# joint — i.e. the actuator must retain at least this multiple of headroom above the
# gravity-compensation torque, equivalently gravity comp may use at most `1/multiple` of the
# per-joint effort limit. 1.25 (an 80% utilisation ceiling, a standard actuator derating)
# is calibrated against the committed v2 inertia at the worst-extension pose (shoulder out
# horizontal): the rated nominal 4.1 kg loads J2 to ~0.73 of its 40 Nm limit and stays
# admissible (honouring the FR-MAN-038 rated hold duty), while the 6.0 kg peak loads J2 to
# ~0.93 — near saturation, where any disturbance drops the brakeless arm — and is refused.
# It is a tunable derating, not a measured value; the 20% reserve covers friction, model
# error, and downward hand disturbance during hand-guiding.
EFFORT_SATURATION_SAFETY_MULTIPLE = 1.25

# The MJCF body a payload/end-effector rigidly attaches to: the wrist-distal body carrying
# joint7 (`ee_base_link` in the vendored v2 asset; "link7" in URDF terms). `Arm.value` is the
# side token ("right"/"left"), so the per-arm body name is this template formatted with it.
EE_ATTACH_BODY_TEMPLATE = "openarm_{side}_ee_base_link"

# Environment variable pointing the deferred live-registration re-verification hook at a
# directory of real static-hold captures (a mounted payload, torque-ON hold, measured joint
# torque). Until it is set, the on-hardware registration acceptance skips with a reason and
# is never asserted green — the model math runs here, the live measurement is deferred.
PAYLOAD_FIXTURE_ENV_VAR = "OPENARM_PAYLOAD_REAL_FIXTURE"
