"""Acceptance ②: gravity torque over the effort-limit safety multiple refuses Freedrive entry.

At the worst extension the peak payload drives the shoulder gravity torque near the joint's
effort limit, where any disturbance drops the brakeless arm; the preflight must refuse entry.
The rated nominal payload at the same pose is the FR-MAN-038 hold duty and must stay
admissible — a preflight that refused it would be a false alarm that blocks legitimate use.
"""

from __future__ import annotations

import pytest

from backend.gravity import Arm, MuJoCoV2GravityBackend
from backend.payload import (
    EFFORT_SATURATION_SAFETY_MULTIPLE,
    FreedrivePreflight,
    Payload,
    PayloadError,
    PayloadGravityModel,
)
from backend.safety_bringup.constants import URDF_EFFORT_LIMIT_NM

_J2 = 1


def test_peak_payload_worst_extension_refused(right_model, worst_extension_pose) -> None:
    # ②: 6.0 kg at worst extension saturates the shoulder — entry refused.
    right_model.registry.register(Payload.at_mount(6.0, "peak"))
    decision = FreedrivePreflight(right_model).check(worst_extension_pose)
    assert not decision.admitted
    assert _J2 in decision.offending_joints
    assert decision.utilisation[_J2] > 1.0
    assert "refused" in decision.reason.lower()


def test_nominal_payload_worst_extension_admitted(right_model, worst_extension_pose) -> None:
    # ②: the rated 4.1 kg hold-at-max-extension duty stays admissible (FR-MAN-038 note).
    right_model.registry.register(Payload.at_mount(4.1, "nominal"))
    decision = FreedrivePreflight(right_model).check(worst_extension_pose)
    assert decision.admitted
    assert decision.offending_joints == ()
    assert decision.utilisation[_J2] < 1.0


def test_bare_arm_worst_extension_admitted(right_model, worst_extension_pose) -> None:
    decision = FreedrivePreflight(right_model).check(worst_extension_pose)
    assert decision.admitted


def test_peak_payload_folded_pose_admitted(right_model, folded_pose) -> None:
    # Same heavy payload, but a compact pose has little gravity torque — admitted.
    right_model.registry.register(Payload.at_mount(6.0, "peak"))
    decision = FreedrivePreflight(right_model).check(folded_pose)
    assert decision.admitted


def test_utilisation_is_multiple_times_torque_over_limit(right_model, worst_extension_pose) -> None:
    right_model.registry.register(Payload.at_mount(6.0, "peak"))
    decision = FreedrivePreflight(right_model).check(worst_extension_pose)
    for index in range(7):
        expected = (
            decision.safety_multiple * abs(decision.tau_nm[index]) / URDF_EFFORT_LIMIT_NM[index]
        )
        assert decision.utilisation[index] == pytest.approx(expected)
    assert decision.effort_limit_nm == URDF_EFFORT_LIMIT_NM
    assert decision.safety_multiple == EFFORT_SATURATION_SAFETY_MULTIPLE


def test_preflight_refuses_trimmed_gravity_model(worst_extension_pose) -> None:
    # A trimmed gravity model would hide saturation, so the preflight refuses to verdict on it.
    trimmed = PayloadGravityModel(Arm.RIGHT, backend=MuJoCoV2GravityBackend(Arm.RIGHT, 0.8))
    trimmed.registry.register(Payload.at_mount(6.0, "peak"))
    with pytest.raises(PayloadError, match="untrimmed gravity model"):
        FreedrivePreflight(trimmed).check(worst_extension_pose)


def test_preflight_rejects_bad_safety_multiple(right_model) -> None:
    with pytest.raises(PayloadError, match="safety multiple must be >= 1"):
        FreedrivePreflight(right_model, safety_multiple=0.9)
