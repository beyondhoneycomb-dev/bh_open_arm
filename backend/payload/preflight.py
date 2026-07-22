"""The pre-Freedrive effort-saturation check (FR-MAN-038).

Before Freedrive entry the gravity-compensation torque at the current pose must stay within a
safety multiple of each joint's effort limit; over an over-large payload or the worst
extension the compensation torque saturates the actuator, and a saturated brakeless arm
drops. This module renders that go/no-go verdict from the payload-reflected gravity model.

The effort limit (40/40/27/27/7/7/7 Nm) is imported from its single source in
`backend.safety_bringup`, not re-declared here. The verdict is refused — not merely
tightened — because a refusal a caller can ignore is not a safety gate; entry is declined and
the offending joints are named so the operator can correct the registration or change the
pose (spec 04 §"Freedrive 중력 토크 포화").
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from backend.dynamics.constants import ARM_JOINT_COUNT
from backend.gravity.constants import GRAVITY_SCALE_DEFAULT
from backend.payload.constants import EFFORT_SATURATION_SAFETY_MULTIPLE
from backend.payload.errors import PayloadError
from backend.payload.gravity_reflection import PayloadGravityModel
from backend.safety_bringup.constants import URDF_EFFORT_LIMIT_NM

_SCALE_ABS_TOL = 1.0e-9


@dataclass(frozen=True)
class EffortSaturationDecision:
    """The pre-Freedrive effort-saturation verdict for one pose.

    Attributes:
        admitted: True when every joint stays within the safety-derated effort limit.
        tau_nm: Per-joint gravity torque (payload reflected) evaluated, Nm.
        effort_limit_nm: Per-joint effort limit checked against, Nm.
        safety_multiple: The FR-MAN-038 multiple applied (torque times this must fit the limit).
        utilisation: Per-joint `safety_multiple * |tau| / limit`; > 1.0 means the joint fails.
        offending_joints: Zero-based indices of the joints that exceeded the derated limit.
        reason: Empty when admitted; otherwise names the offending joints and utilisations.
    """

    admitted: bool
    tau_nm: tuple[float, ...]
    effort_limit_nm: tuple[float, ...]
    safety_multiple: float
    utilisation: tuple[float, ...]
    offending_joints: tuple[int, ...]
    reason: str


class FreedrivePreflight:
    """Renders the FR-MAN-038 effort-saturation verdict from a payload gravity model."""

    def __init__(
        self,
        model: PayloadGravityModel,
        effort_limit_nm: Sequence[float] = URDF_EFFORT_LIMIT_NM,
        safety_multiple: float = EFFORT_SATURATION_SAFETY_MULTIPLE,
    ) -> None:
        """Bind the preflight to a gravity model, effort limits, and the safety multiple.

        Args:
            model: The payload-reflected gravity model; its registry holds the current payload.
            effort_limit_nm: Per-joint effort limit, Nm. Defaults to the URDF effort limit.
            safety_multiple: The FR-MAN-038 multiple, > 1. Defaults to the documented derating.

        Raises:
            PayloadError: On a wrong-width effort vector or a multiple that is not >= 1.
        """
        self._model = model
        limits = tuple(float(value) for value in effort_limit_nm)
        if len(limits) != ARM_JOINT_COUNT:
            raise PayloadError(
                f"effort limit must have {ARM_JOINT_COUNT} entries, got {len(limits)}"
            )
        multiple = float(safety_multiple)
        if not multiple >= 1.0:
            raise PayloadError(f"safety multiple must be >= 1, got {multiple}")
        self._effort_limit = limits
        self._safety_multiple = multiple

    def check(self, q: Sequence[float]) -> EffortSaturationDecision:
        """Return the effort-saturation verdict for pose `q` with the registered payload.

        Args:
            q: The arm's seven joint angles, v2 convention, radians.

        Returns:
            (EffortSaturationDecision) Admitted only when every joint's gravity torque times
            the safety multiple fits its effort limit.

        Raises:
            PayloadError: On a wrong-width pose, or when the gravity model is trimmed
                (`gravity_scale != 1.0`) — a trimmed model under- or over-states the true
                holding torque, so a saturation verdict on it would be misleading.
        """
        if not math.isclose(
            self._model.gravity_scale, GRAVITY_SCALE_DEFAULT, abs_tol=_SCALE_ABS_TOL
        ):
            raise PayloadError(
                f"effort preflight requires an untrimmed gravity model "
                f"(gravity_scale == {GRAVITY_SCALE_DEFAULT}), got {self._model.gravity_scale}; "
                "a trimmed model would hide effort saturation"
            )
        tau = self._model.tau_grav(q)
        utilisation = tuple(
            self._safety_multiple * abs(tau[index]) / self._effort_limit[index]
            for index in range(ARM_JOINT_COUNT)
        )
        offending = tuple(index for index, ratio in enumerate(utilisation) if ratio > 1.0)
        reason = "" if not offending else self._refusal_reason(tau, utilisation, offending)
        return EffortSaturationDecision(
            admitted=not offending,
            tau_nm=tau,
            effort_limit_nm=self._effort_limit,
            safety_multiple=self._safety_multiple,
            utilisation=utilisation,
            offending_joints=offending,
            reason=reason,
        )

    def _refusal_reason(
        self,
        tau: tuple[float, ...],
        utilisation: tuple[float, ...],
        offending: tuple[int, ...],
    ) -> str:
        """Compose the human-readable refusal naming each saturated joint."""
        parts = [
            f"joint{index + 1} needs {abs(tau[index]):.1f} Nm, "
            f"{self._safety_multiple:g}x exceeds its {self._effort_limit[index]:g} Nm limit "
            f"(utilisation {utilisation[index]:.2f})"
            for index in offending
        ]
        return "Freedrive entry refused: " + "; ".join(parts)
