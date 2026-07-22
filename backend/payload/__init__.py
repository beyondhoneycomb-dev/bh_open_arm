"""WP-2B-04 — the payload model: a mass/CoG registry reflected into the gravity torque.

FR-SAF-036 / FR-MAN-033 register an end-effector payload (0-6.0 kg, EE included) and require
it to appear in the gravity-compensation model, so a payload change is not mistaken for a
constant collision residual. FR-MAN-038 refuses Freedrive entry when the gravity torque at
the current pose would saturate a joint's effort limit. This package builds all three on top
of WP-2B-02's single `tau_grav(q)` compute point.

Public surface:

* `Payload` / `PayloadRegistry` — the validated payload value and the single-payload registry
  (register/unregister/current). An out-of-band mass or a units-error CoG cannot construct.
* `PayloadGravityModel` — the reflection path: WP-2B-02's base gravity plus the registered
  payload's point-mass delta, so register/unregister moves `tau_grav` by exactly the payload
  contribution (acceptance ①).
* `FreedrivePreflight` / `EffortSaturationDecision` — the FR-MAN-038 pre-entry check that
  refuses a pose whose reflected gravity torque exceeds the effort limit's safety multiple
  (acceptance ②).
* `evaluate_collision_misdetection` / `PayloadResidualCheck` / `static_hold_torque` — the
  residual re-verification that a registered payload change does not read as a collision
  (acceptance ③); `collision_threshold_nm` exposes the threshold it compares against.
* `reverify_from_fixture` / `fixture_dir_from_env` / `RealPayloadVerification` — the deferred
  on-hardware live-registration re-verification hook (phase 2), never asserted green here.
"""

from __future__ import annotations

from backend.payload.constants import (
    EFFORT_SATURATION_SAFETY_MULTIPLE,
    PAYLOAD_FIXTURE_ENV_VAR,
    PAYLOAD_MASS_MAX_KG,
    PAYLOAD_MASS_MIN_KG,
    PAYLOAD_MASS_NOMINAL_KG,
)
from backend.payload.detection import (
    PayloadResidualCheck,
    collision_threshold_nm,
    evaluate_collision_misdetection,
    payload_change_residual,
    static_hold_torque,
)
from backend.payload.errors import PayloadError
from backend.payload.gravity_reflection import PayloadGravityModel
from backend.payload.payload import Payload
from backend.payload.preflight import EffortSaturationDecision, FreedrivePreflight
from backend.payload.registry import PayloadRegistry
from backend.payload.reverify import (
    RealPayloadVerification,
    fixture_dir_from_env,
    reverify_from_fixture,
)

__all__ = [
    "EFFORT_SATURATION_SAFETY_MULTIPLE",
    "PAYLOAD_FIXTURE_ENV_VAR",
    "PAYLOAD_MASS_MAX_KG",
    "PAYLOAD_MASS_MIN_KG",
    "PAYLOAD_MASS_NOMINAL_KG",
    "EffortSaturationDecision",
    "FreedrivePreflight",
    "Payload",
    "PayloadError",
    "PayloadGravityModel",
    "PayloadRegistry",
    "PayloadResidualCheck",
    "RealPayloadVerification",
    "collision_threshold_nm",
    "evaluate_collision_misdetection",
    "fixture_dir_from_env",
    "payload_change_residual",
    "reverify_from_fixture",
    "static_hold_torque",
]
