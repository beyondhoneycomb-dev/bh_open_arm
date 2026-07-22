"""One tick's audit record — the pre-conversion request preserved beside everything else.

The contract WP-2A-05 exists to hold (`00` §8.3, `04` FR-MAN-004) is that the
**original request** and the **post-clamp accepted action** are recorded together.
This record does not re-implement that rule: it embeds the Wave-1 `GateFrame`, whose
shape already makes both channels mandatory and a one-sided frame unconstructible
(`backend.actuation.enforcement`). Recording that frame is how "both channels, always"
reaches the ring — importing the rule, never restating it.

Around the frame it carries the rest of the SPINE §6 audit channels the ring window
retains: the `executedMitCommand` batch the scheduler emitted, the `safetyOverride`
(clamp reason plus stale and latch flags), and the calibration transform chain that
makes an offset double-add or miss detectable. The physical-telemetry channels
(`q̇, τ_meas, τ_model, r, ERR, T_MOS, T_Rotor`, `12` FR-SAF-065) are a separate,
downstream concern owned by WP-2C-09, which consumes this ring; they are deliberately
not fields here.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.actuation import GateFrame, GateResult
from backend.audit.transform import JointTransform
from contracts.action import ClampReason, ExecutedMitCommand, SafetyOverride
from contracts.units import Deg


@dataclass(frozen=True)
class AuditRecord:
    """A single tick's full audit entry retained in the ring.

    Attributes:
        tick_index: Monotonic tick number from torque-on (`backend.actuation.trace`).
        at: Monotonic clock reading for this record, seconds — the retention axis.
        frame: The Wave-1 request/accepted pair; both channels mandatory by its shape.
        executed: The MIT batch the scheduler emitted this tick (audit-only).
        override: Why the accepted action differs from the request (clamp reason,
            stale, latch).
        chain: The per-joint calibration transform, for offset double-add / miss
            detection.
    """

    tick_index: int
    at: float
    frame: GateFrame
    executed: tuple[ExecutedMitCommand, ...]
    override: SafetyOverride
    chain: tuple[JointTransform, ...]

    @property
    def requested(self) -> tuple[Deg, ...]:
        """The producer's pre-clamp position request, degrees."""
        return self.frame.requested

    @property
    def accepted(self) -> tuple[Deg, ...]:
        """The post-clamp position actually admitted, degrees."""
        return self.frame.accepted

    @property
    def clamp_reason(self) -> ClampReason:
        """Why the accepted action was clamped away from the request, if it was."""
        return self.override.clamp_reason

    @property
    def stale(self) -> bool:
        """Whether the source mailbox was stale this tick."""
        return self.override.stale

    @property
    def latched(self) -> bool:
        """Whether a safety latch was held this tick (until operator ack)."""
        return self.override.latched

    @property
    def clamped(self) -> bool:
        """Whether request and accepted differ — a clamp fired this tick."""
        return self.frame.requested != self.frame.accepted

    @classmethod
    def from_decision(
        cls,
        *,
        tick_index: int,
        at: float,
        requested: tuple[Deg, ...],
        result: GateResult,
        executed: tuple[ExecutedMitCommand, ...],
        chain: tuple[JointTransform, ...],
    ) -> AuditRecord:
        """Assemble a record from one gateway decision, reusing its request/accepted pair.

        The `GateFrame` is built from the request and the decision's accepted action,
        so the "both channels, always" rule is honoured by construction rather than
        re-checked here.

        Args:
            tick_index: Monotonic tick number.
            at: Monotonic clock reading, seconds.
            requested: The pre-clamp request the decision was made from, degrees.
            result: The gateway's decision, source of the accepted action and override.
            executed: The MIT batch emitted this tick.
            chain: The per-joint calibration transform for this tick.

        Returns:
            (AuditRecord) The composed record.
        """
        return cls(
            tick_index=tick_index,
            at=at,
            frame=GateFrame(requested=requested, accepted=result.accepted),
            executed=executed,
            override=result.override,
            chain=chain,
        )
