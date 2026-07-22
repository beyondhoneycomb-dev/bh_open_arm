"""The per-reason Move-to check report and its execution result.

Acceptance ② requires the checks' outcome to be shown *per reason*, so the report does
not collapse to a single boolean — it carries the individual findings, each naming the
reused primitive's own reason (``JogClampReason`` from WP-2A-03 for a limit violation,
``JogStopReason`` from WP-2D-01 for an IK-existence failure). No third reason vocabulary
is minted here: the finer meanings live where their check lives, and this module only
groups them for display.

``passed`` is the single gate the executor reads; ``by_reason`` is the operator-facing
grouping. A report is produced by the gate's *check* step and is inert — holding one has
no side effect on the arm.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from backend.cartesian_jog import JogStopReason
from backend.jogclamp import JogClampReason
from contracts.action.channels import AcceptedPositionAction
from contracts.units import Deg


@dataclass(frozen=True)
class LimitFinding:
    """One arm joint whose Move-to value left the limit envelope.

    A ``MECHANICAL_LIMIT`` finding is the outer fault — the raw request left the URDF
    envelope; an ``OPERATIONAL_LIMIT`` finding is a value inside the mechanical bound
    but outside the tighter operational one. The two stay distinct because WP-2A-03
    keeps them distinct, and a Move-to that could not tell them apart could not explain
    why it refused (acceptance ②).

    Attributes:
        side: The arm the joint belongs to.
        joint_number: The human joint number (joint1..joint7).
        slot: The 16-dim solution/limit slot the joint occupies.
        reason: Which envelope was violated (mechanical or operational).
        value_deg: The offending value, degrees.
        lower_deg: The violated envelope's lower bound, degrees.
        upper_deg: The violated envelope's upper bound, degrees.
    """

    side: str
    joint_number: int
    slot: int
    reason: JogClampReason
    value_deg: float
    lower_deg: float
    upper_deg: float

    def message(self) -> str:
        """Return a one-line operator-facing description of the violation."""
        return (
            f"{self.side} joint{self.joint_number}: {self.value_deg:.3f}° outside "
            f"{self.reason.value} [{self.lower_deg:.3f}°, {self.upper_deg:.3f}°]"
        )


@dataclass(frozen=True)
class IkExistenceFinding:
    """The reason no admissible IK solution exists for an EE-pose Move-to.

    Only ever present on an EE-pose request; a joint request carries no IK check. The
    reason is WP-2D-01's own ``JogStopReason`` — the same category the jog would hold
    on — so the Move-to and the jog explain an unreachable pose identically.

    Attributes:
        reason: The jog's stop category (no solution, limit, singularity, residual,
            unconstrained fallback).
        detail: Human-readable context from the jog probe.
    """

    reason: JogStopReason
    detail: str

    def message(self) -> str:
        """Return a one-line operator-facing description of the IK failure."""
        return f"IK-existence: {self.reason.value}" + (f" — {self.detail}" if self.detail else "")


@dataclass(frozen=True)
class MoveToCheckReport:
    """The outcome of the pre-execution checks for one Move-to request.

    Inert by construction: producing one runs the checks but moves nothing. ``passed``
    is true only when every applicable check passed, and it is the sole condition the
    executor gates on.

    Attributes:
        kind: ``"joint"`` or ``"pose"`` — which input was checked.
        side: The arm the request targets.
        ik_checked: Whether the IK-existence check applied (true only for a pose).
        limit_findings: Every joint that left the envelope, empty when the limit check
            passed.
        ik_finding: The IK-existence failure, or None when it passed or did not apply.
    """

    kind: str
    side: str
    ik_checked: bool
    limit_findings: tuple[LimitFinding, ...] = ()
    ik_finding: IkExistenceFinding | None = None

    @property
    def limit_ok(self) -> bool:
        """Whether the limit check found no violation."""
        return not self.limit_findings

    @property
    def ik_ok(self) -> bool:
        """Whether the IK-existence check passed (vacuously true when not applied)."""
        return self.ik_finding is None

    @property
    def passed(self) -> bool:
        """Whether every applicable check passed — the executor's gate."""
        return self.limit_ok and self.ik_ok

    def by_reason(self) -> dict[str, list[str]]:
        """Group every finding's message under its reason, for a per-reason display.

        Returns:
            (dict[str, list[str]]) Reason value to the messages recorded under it;
            empty when the request passed. IK reasons and limit reasons share the one
            mapping so a UI renders a single per-reason list (acceptance ②).
        """
        grouped: dict[str, list[str]] = {}
        for finding in self.limit_findings:
            grouped.setdefault(finding.reason.value, []).append(finding.message())
        if self.ik_finding is not None:
            grouped.setdefault(self.ik_finding.reason.value, []).append(self.ik_finding.message())
        return grouped


@dataclass(frozen=True)
class MoveToResult:
    """What the gate did with a request: the checks, and whether it executed.

    ``executed`` is true only when ``report.passed`` was true and the commit advanced
    the arm state. On a refusal ``executed`` is false, ``committed_solution`` is None,
    and ``report`` carries the per-reason explanation — the arm did not move.

    Attributes:
        executed: Whether the move committed. False whenever the checks did not pass.
        report: The per-reason check report the decision was made on.
        committed_solution: The 16-dim configuration after a committed move, else None.
        accepted: The gateway-bound accepted action from an EE commit, else None.
        detail: Human-readable context for the operator log.
    """

    executed: bool
    report: MoveToCheckReport
    committed_solution: np.ndarray | None = None
    accepted: AcceptedPositionAction | None = None
    detail: str = ""


def limit_findings_from_config(
    config_deg: tuple[Deg, ...],
    mechanical_clamped: tuple[Deg, ...],
    operational_clamped: tuple[Deg, ...],
    envelope_mechanical: tuple[tuple[Deg, Deg], ...],
    envelope_operational: tuple[tuple[Deg, Deg], ...],
    side: str,
    slots: tuple[int, ...],
    first_human_joint_number: int,
) -> tuple[LimitFinding, ...]:
    """Attribute per-joint limit violations from WP-2A-03's clamp outputs.

    The two clamped vectors are what ``JogClampPath.clamp_stage1`` and ``clamp_stage2``
    returned for the same request; a slot whose mechanical-clamped value differs from
    the request left the mechanical envelope, and a slot merely operational-clamped
    (inside mechanical, outside operational) is the tighter, normal violation. This
    function does not re-clip — it only reads the difference the reused clamp already
    computed, so there is no second copy of the bound comparison.

    Args:
        config_deg: The full request configuration, degrees.
        mechanical_clamped: ``clamp_stage1(config)`` output.
        operational_clamped: ``clamp_stage2(config)`` output.
        envelope_mechanical: The mechanical ``(low, high)`` envelope, for the message.
        envelope_operational: The operational ``(low, high)`` envelope, for the message.
        side: The arm the checked slots belong to.
        slots: The slots to report on (the moved side's arm joints).
        first_human_joint_number: The joint number the first reported slot maps to.

    Returns:
        (tuple[LimitFinding, ...]) One finding per violating slot, mechanical first.
    """
    findings: list[LimitFinding] = []
    for offset, slot in enumerate(slots):
        requested = config_deg[slot].value
        mech_low, mech_high = envelope_mechanical[slot]
        op_low, op_high = envelope_operational[slot]
        joint_number = first_human_joint_number + offset
        if mechanical_clamped[slot].value != requested:
            findings.append(
                LimitFinding(
                    side=side,
                    joint_number=joint_number,
                    slot=slot,
                    reason=JogClampReason.MECHANICAL_LIMIT,
                    value_deg=requested,
                    lower_deg=mech_low.value,
                    upper_deg=mech_high.value,
                )
            )
        elif operational_clamped[slot].value != requested:
            findings.append(
                LimitFinding(
                    side=side,
                    joint_number=joint_number,
                    slot=slot,
                    reason=JogClampReason.OPERATIONAL_LIMIT,
                    value_deg=requested,
                    lower_deg=op_low.value,
                    upper_deg=op_high.value,
                )
            )
    return tuple(findings)
