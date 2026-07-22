"""The gravity-torque effort-saturation check gating Freedrive entry (WP-2D-03 acceptance IV).

Path (C) compensates gravity by feeding ``tau_grav(q)`` forward. That only works while the
actuator has effort to spare: if gravity alone already needs the joint's full peak torque at the
entry pose, there is no headroom to also hold against a hand-guide or add friction compensation,
and entering Freedrive there would let the arm sag despite "compensation". This check computes
the gravity term at the entry pose and refuses entry when any joint's gravity torque reaches a
configured fraction of its peak torque.

The peak-torque envelope is the ``SafetyLimits.peak_torque_nm`` the gateway also enforces — one
source for the effort a saturation check and a torque clamp both read, never a second copy.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from backend.freedrive.constants import DEFAULT_EFFORT_HEADROOM
from backend.gravity.backend import GravityBackend
from contracts.units import Nm


@dataclass(frozen=True)
class EffortSaturation:
    """The verdict of one entry-pose effort-saturation check.

    Attributes:
        saturated: True when any joint's gravity torque reaches the headroom fraction of its peak
            torque — Freedrive entry is refused.
        tau_grav_nm: The per-joint gravity torque at the entry pose, Nm.
        peak_torque_nm: The per-joint peak torque the fraction is taken of, Nm.
        per_joint_saturated: Which joints individually reached the headroom fraction.
        headroom: The peak-torque fraction the gravity term had to stay under.
    """

    saturated: bool
    tau_grav_nm: tuple[float, ...]
    peak_torque_nm: tuple[float, ...]
    per_joint_saturated: tuple[bool, ...]
    headroom: float


class EffortSaturationCheck:
    """Refuse Freedrive entry when gravity torque saturates the actuator effort at the pose."""

    def __init__(
        self,
        gravity_backend: GravityBackend,
        peak_torque_nm: Sequence[Nm],
        headroom: float = DEFAULT_EFFORT_HEADROOM,
    ) -> None:
        """Bind the check to a gravity backend and the peak-torque envelope it shares.

        Args:
            gravity_backend: The single ``tau_grav(q)`` source (WP-2B-02).
            peak_torque_nm: Per-joint peak torque, the same ``SafetyLimits`` the gateway enforces.
            headroom: The peak fraction the gravity term must stay under to admit entry, in (0, 1].

        Raises:
            ValueError: If ``headroom`` is not in (0, 1].
        """
        if not 0.0 < headroom <= 1.0:
            raise ValueError(f"headroom must be in (0, 1], got {headroom}")
        self._gravity_backend = gravity_backend
        self._peak_torque_nm = tuple(float(value.value) for value in peak_torque_nm)
        self._headroom = headroom

    def check(self, q_entry: Sequence[float]) -> EffortSaturation:
        """Evaluate whether gravity torque saturates the effort at an entry pose.

        Args:
            q_entry: The entry joint angles, v2 convention, radians, arm width.

        Returns:
            (EffortSaturation) The per-joint verdict; ``saturated`` refuses entry.

        Raises:
            ValueError: If the pose width does not match the peak-torque width.
        """
        tau_grav = self._gravity_backend.tau_grav(q_entry)
        if len(tau_grav) != len(self._peak_torque_nm):
            raise ValueError(
                f"gravity torque width {len(tau_grav)} does not match peak-torque width "
                f"{len(self._peak_torque_nm)}"
            )
        per_joint = tuple(
            abs(torque) >= self._headroom * abs(peak)
            for torque, peak in zip(tau_grav, self._peak_torque_nm, strict=True)
        )
        return EffortSaturation(
            saturated=any(per_joint),
            tau_grav_nm=tuple(float(value) for value in tau_grav),
            peak_torque_nm=self._peak_torque_nm,
            per_joint_saturated=per_joint,
            headroom=self._headroom,
        )
