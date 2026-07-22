"""The Freedrive command path, as a scheduler producer (WP-2D-03, spec 04 FR-MAN-030).

Path (C) commands ``(kp=0, kd=kd_freedrive, q, dq=0, tau=tau_grav(q)+tau_fric(dq))`` per joint.
This producer builds exactly that, reusing the single ``tau_grav`` source (WP-2B-02) and the
identified friction law (WP-2B-07) for the feed-forward term.

It never reaches the bus. Like any scheduler producer it holds no CAN handle (the single-writer
invariant, ``02a`` §3.1 ①); the frame it builds is routed through the one enforcement gateway —
the same ``ActuationGateway`` the ``send_action`` override delegates to (I-4). That gateway
validates the MIT gains (``kp=0`` and ``kd_freedrive`` against the encoder bands) and clamps the
feed-forward torque to Peak Torque before the command is assembled from its verdict. So Freedrive
releases the position path's tau-zero constraint through the sanctioned torque channel while the
gateway stays the single point every command source passes — releasing the constraint is not the
same as opening a second write path, and this producer opens none.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from backend.actuation.enforcement import ActuationGateway
from backend.actuation.safety import KD_MAX, KD_MIN, SafetyReason
from backend.freedrive.constants import FREEDRIVE_DQ, FREEDRIVE_KP, FREEDRIVE_PRODUCER_ID
from backend.friction.model import FrictionParams
from backend.gravity.backend import GravityBackend
from contracts.action import ExecutedMitCommand
from contracts.units import Nm, Rad, deg_to_rad, rad_to_deg


@dataclass(frozen=True)
class FreedriveFrame:
    """One Freedrive control frame the producer built for the entry pose it was given.

    Attributes:
        engaged: True when the gateway admitted the command and ``commands`` drives the arm;
            False when the gateway held (a collision latch, a stale source), and ``commands`` is
            empty — the caller then holds position rather than back-driving blind.
        commands: The per-joint MIT commands ``(kp=0, kd=kd_fd, q, dq=0, tau)`` when engaged.
        tau_grav_nm: The per-joint gravity term fed forward, Nm.
        tau_fric_nm: The per-joint friction term fed forward, Nm.
        feedforward_nm: The per-joint feed-forward torque after the gateway's Peak-Torque clamp.
        hold_reason: The gateway's stop reason when not engaged, else None.
    """

    engaged: bool
    commands: tuple[ExecutedMitCommand, ...]
    tau_grav_nm: tuple[float, ...]
    tau_fric_nm: tuple[float, ...]
    feedforward_nm: tuple[float, ...]
    hold_reason: SafetyReason | None


class FreedriveProducer:
    """Builds the path-(C) MIT command through the single gateway; holds no CAN handle.

    Not thread-safe: one producer serves one Freedrive session, calling its gravity backend's
    private mujoco scratch buffer each frame. It satisfies the scheduler ``Producer`` surface
    (``producer_id`` + ``join``) so it can be swapped in as the active producer, but its privilege
    is only building a frame — the gateway enforces and the single writer emits.
    """

    def __init__(
        self,
        gravity_backend: GravityBackend,
        friction_params: tuple[FrictionParams, ...],
        gateway: ActuationGateway,
        kd_freedrive: tuple[float, ...],
    ) -> None:
        """Wire the producer to its dynamics sources, the gateway, and the per-joint damping.

        Args:
            gravity_backend: The single ``tau_grav(q)`` source (WP-2B-02).
            friction_params: Per-joint identified friction law (WP-2B-07), arm width.
            gateway: The single enforcement gateway (I-4) the frame is routed through.
            kd_freedrive: Per-joint Freedrive damping, each validated against ``[KD_MIN, KD_MAX]``.

        Raises:
            ValueError: If the friction/damping widths disagree, or a damping gain is out of band.
        """
        if len(friction_params) != len(kd_freedrive):
            raise ValueError(
                f"friction width {len(friction_params)} does not match damping width "
                f"{len(kd_freedrive)}"
            )
        for index, gain in enumerate(kd_freedrive):
            if not KD_MIN <= gain <= KD_MAX:
                raise ValueError(
                    f"kd_freedrive[{index}]={gain} is outside the MIT damping band "
                    f"[{KD_MIN}, {KD_MAX}]"
                )
        self._gravity_backend = gravity_backend
        self._friction_params = friction_params
        self._gateway = gateway
        self._kd_freedrive = kd_freedrive
        self._width = len(kd_freedrive)
        self._joined = False

    @property
    def producer_id(self) -> str:
        """Stable identity used in traces and swap accounting.

        Returns:
            (str) The Freedrive producer id.
        """
        return FREEDRIVE_PRODUCER_ID

    @property
    def joined(self) -> bool:
        """Whether this producer has been joined (swapped out and released).

        Returns:
            (bool) True after :meth:`join`.
        """
        return self._joined

    @property
    def kd_freedrive(self) -> tuple[float, ...]:
        """The per-joint Freedrive damping gains in force.

        Returns:
            (tuple[float, ...]) The damping gains, arm width.
        """
        return self._kd_freedrive

    def produce_frame(
        self, q_rad: tuple[float, ...], dq_rad_s: tuple[float, ...]
    ) -> FreedriveFrame:
        """Build one path-(C) frame at a joint state, routed through the single gateway.

        Args:
            q_rad: Present joint angles, v2 convention, radians, arm width.
            dq_rad_s: Present joint velocities, radians per second, arm width.

        Returns:
            (FreedriveFrame) The engaged MIT command, or a held frame when the gateway stopped it.

        Raises:
            ValueError: If a joint-state width does not match the producer width.
        """
        if len(q_rad) != self._width or len(dq_rad_s) != self._width:
            raise ValueError(
                f"joint-state widths ({len(q_rad)}, {len(dq_rad_s)}) do not match producer width "
                f"{self._width}"
            )
        tau_grav = tuple(float(value) for value in self._gravity_backend.tau_grav(q_rad))
        tau_fric = tuple(
            float(params.tau(np.asarray([speed], dtype=np.float64))[0])
            for params, speed in zip(self._friction_params, dq_rad_s, strict=True)
        )
        feedforward = tuple(Nm(g + f) for g, f in zip(tau_grav, tau_fric, strict=True))
        request_deg = tuple(rad_to_deg(Rad(angle)) for angle in q_rad)

        result = self._gateway.submit(
            request_deg,
            request_deg,
            calibrated=True,
            source_age_sec=0.0,
            feedforward_torque_nm=feedforward,
            kp=tuple(FREEDRIVE_KP for _ in range(self._width)),
            kd=self._kd_freedrive,
        )

        if result.rejected:
            return FreedriveFrame(
                engaged=False,
                commands=(),
                tau_grav_nm=tau_grav,
                tau_fric_nm=tau_fric,
                feedforward_nm=tuple(value.value for value in result.feedforward_torque_nm),
                hold_reason=result.reason,
            )

        commands = tuple(
            ExecutedMitCommand(
                kp=FREEDRIVE_KP,
                kd=gain,
                q=deg_to_rad(accepted),
                dq=FREEDRIVE_DQ,
                tau=torque,
            )
            for accepted, gain, torque in zip(
                result.accepted, self._kd_freedrive, result.feedforward_torque_nm, strict=True
            )
        )
        return FreedriveFrame(
            engaged=True,
            commands=commands,
            tau_grav_nm=tau_grav,
            tau_fric_nm=tau_fric,
            feedforward_nm=tuple(value.value for value in result.feedforward_torque_nm),
            hold_reason=None,
        )

    def join(self) -> None:
        """Release the producer. Idempotent; a double join is not an error."""
        self._joined = True
