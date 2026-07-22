"""Payload-change re-verification: proving a payload change is not read as a collision.

A momentum/torque-residual collision detector (WP-2C-01) watches `r = tau_meas - tau_model`.
If a payload changes but the gravity model does not, `tau_model` is wrong by the payload's
gravity contribution and `r` carries a constant offset — which, once detection is active,
reads as a permanent false or missed collision (the FR-MAN-033 / FR-SAF-036 failure). This
module is the model-side check that the offset is gone once the payload is registered: the
residual against the payload-reflected model must fall below the per-joint collision
threshold.

The collision threshold is imported from its single source in `backend.safety_bringup`
(FR-SAF-020, the ±10%-of-effort default). The residual math runs on this host; live
re-verification against a torque-ON static-hold measurement is the deferred hook in
`reverify` — this module is what that hook calls, so the offline acceptance and the on-
hardware re-verification apply the identical test.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from backend.dynamics.constants import ARM_JOINT_COUNT
from backend.payload.errors import PayloadError
from backend.payload.gravity_reflection import PayloadGravityModel
from backend.payload.payload import Payload
from backend.safety_bringup.thresholds import default_collision_thresholds


@dataclass(frozen=True)
class PayloadResidualCheck:
    """The residual verdict for a payload change at one pose.

    Attributes:
        residual_nm: Per-joint `tau_meas - tau_model` against the reflected model, Nm.
        threshold_nm: Per-joint collision threshold compared against, Nm.
        offending_joints: Zero-based indices whose residual magnitude exceeds the threshold.
        misdetected: True when any joint's residual would trip the collision detector — i.e.
            the payload change WOULD be read as a collision at this pose.
    """

    residual_nm: tuple[float, ...]
    threshold_nm: tuple[float, ...]
    offending_joints: tuple[int, ...]
    misdetected: bool


def collision_threshold_nm() -> tuple[float, ...]:
    """Return the per-joint default collision threshold (FR-SAF-020), Nm.

    Returns:
        (tuple[float, ...]) The ±10%-of-effort default thresholds, joint1..joint7.
    """
    return default_collision_thresholds().thresholds_nm


def static_hold_torque(
    model: PayloadGravityModel, q: Sequence[float], payload: Payload | None
) -> tuple[float, ...]:
    """Return the gravity-compensation torque needed to hold `payload` static at pose `q`.

    This is the arm's own gravity plus the payload's gravity delta — the torque a torque-ON
    static hold produces at this pose in the absence of friction and contact. It is a modelled
    quantity, not a measurement; the acceptance test uses it as the synthetic `tau_meas`, and
    the deferred hook replaces it with a real captured measurement.

    Args:
        model: The payload-reflected gravity model.
        q: The arm's seven joint angles, v2 convention, radians.
        payload: The payload physically held, or None.

    Returns:
        (tuple[float, ...]) Per-joint static-hold torque, Nm.
    """
    base = model.base_tau_grav(q)
    delta = model.payload_delta(q, payload)
    return tuple(base[index] + delta[index] for index in range(ARM_JOINT_COUNT))


def payload_change_residual(
    model: PayloadGravityModel, q: Sequence[float], measured_tau_nm: Sequence[float]
) -> tuple[float, ...]:
    """Return `tau_meas - tau_model` at pose `q` against the payload-reflected model.

    Args:
        model: The payload-reflected gravity model; its registry holds the registered payload.
        q: The arm's seven joint angles, v2 convention, radians.
        measured_tau_nm: The measured (or synthetic static-hold) joint torque, Nm.

    Returns:
        (tuple[float, ...]) Per-joint residual, Nm.

    Raises:
        PayloadError: On a measured-torque vector of the wrong width.
    """
    measured = tuple(float(value) for value in measured_tau_nm)
    if len(measured) != ARM_JOINT_COUNT:
        raise PayloadError(
            f"measured torque must have {ARM_JOINT_COUNT} entries, got {len(measured)}"
        )
    model_tau = model.tau_grav(q)
    return tuple(measured[index] - model_tau[index] for index in range(ARM_JOINT_COUNT))


def evaluate_collision_misdetection(
    model: PayloadGravityModel,
    q: Sequence[float],
    measured_tau_nm: Sequence[float],
    threshold_nm: Sequence[float] | None = None,
) -> PayloadResidualCheck:
    """Judge whether a payload change reads as a collision at pose `q`.

    With the payload registered, the residual against the reflected model should be below the
    collision threshold on every joint (`misdetected == False`); with it unregistered, the
    residual carries the payload's gravity contribution and trips the detector.

    Args:
        model: The payload-reflected gravity model.
        q: The arm's seven joint angles, v2 convention, radians.
        measured_tau_nm: The measured (or synthetic static-hold) joint torque, Nm.
        threshold_nm: Per-joint collision threshold, Nm. Defaults to the FR-SAF-020 default.

    Returns:
        (PayloadResidualCheck) The residual and whether it would trip the collision detector.

    Raises:
        PayloadError: On a wrong-width torque or threshold vector.
    """
    residual = payload_change_residual(model, q, measured_tau_nm)
    thresholds = tuple(
        float(value)
        for value in (threshold_nm if threshold_nm is not None else collision_threshold_nm())
    )
    if len(thresholds) != ARM_JOINT_COUNT:
        raise PayloadError(f"threshold must have {ARM_JOINT_COUNT} entries, got {len(thresholds)}")
    offending = tuple(
        index for index in range(ARM_JOINT_COUNT) if abs(residual[index]) > thresholds[index]
    )
    return PayloadResidualCheck(
        residual_nm=residual,
        threshold_nm=thresholds,
        offending_joints=offending,
        misdetected=bool(offending),
    )
