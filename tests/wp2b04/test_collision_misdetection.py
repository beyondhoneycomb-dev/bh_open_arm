"""Acceptance ③: a registered payload change is not mis-detected as a collision.

A torque-residual detector reads `tau_meas - tau_model`. With the payload registered the
model matches the physical hold and the residual is ~0; with it unregistered the residual
carries the whole payload gravity term and trips the detector. The synthetic `tau_meas` is
the modelled static-hold torque of the physically-held payload — the deferred hook replaces
it with a real measurement.
"""

from __future__ import annotations

import pytest

from backend.payload import (
    Payload,
    collision_threshold_nm,
    evaluate_collision_misdetection,
    payload_change_residual,
    static_hold_torque,
)

_REAL_PAYLOAD = Payload.from_cog(3.0, (0.01, -0.02, -0.05), "held-tool")
_POSE = (0.3, 1.2, -0.4, 0.8, 0.2, -0.3, 0.1)


def test_registered_payload_not_misdetected(right_model) -> None:
    # ③: with the payload registered, the residual stays below the collision threshold.
    right_model.registry.register(_REAL_PAYLOAD)
    measured = static_hold_torque(right_model, _POSE, _REAL_PAYLOAD)
    check = evaluate_collision_misdetection(right_model, _POSE, measured)
    assert not check.misdetected
    assert check.offending_joints == ()
    assert all(abs(residual) < 1e-6 for residual in check.residual_nm)


def test_unregistered_payload_is_misdetected(right_model) -> None:
    # ③ contrapositive: the same physical hold, unregistered, reads as a collision.
    measured = static_hold_torque(right_model, _POSE, _REAL_PAYLOAD)  # payload physically present
    right_model.registry.unregister()  # but not registered in the model
    check = evaluate_collision_misdetection(right_model, _POSE, measured)
    assert check.misdetected
    # the shoulder residual is the payload's uncompensated gravity, well over its threshold
    assert 1 in check.offending_joints
    assert abs(check.residual_nm[1]) > check.threshold_nm[1]


def test_wrong_payload_registration_still_misdetected(right_model) -> None:
    # A mis-registration (wrong mass) does not cancel the residual — it is not silently passed.
    right_model.registry.register(Payload.at_mount(1.0, "under-registered"))
    measured = static_hold_torque(right_model, _POSE, _REAL_PAYLOAD)
    check = evaluate_collision_misdetection(right_model, _POSE, measured)
    assert check.misdetected


def test_residual_matches_manual_difference(right_model) -> None:
    right_model.registry.register(_REAL_PAYLOAD)
    measured = (1.0, 2.0, 3.0, 0.5, 0.1, -0.2, 0.0)
    residual = payload_change_residual(right_model, _POSE, measured)
    model_tau = right_model.tau_grav(_POSE)
    for index in range(7):
        assert residual[index] == pytest.approx(measured[index] - model_tau[index])


def test_threshold_is_safety_bringup_default() -> None:
    # The threshold is the single-source FR-SAF-020 default, not a payload-local copy.
    assert collision_threshold_nm() == pytest.approx((4.0, 4.0, 2.7, 2.7, 0.7, 0.7, 0.7))
