"""The save/start bandwidth block for WP-3B-02, layered over the WP-0B-08 formula.

The arithmetic — `W×H×Bpp×8×fps`, the per-profile sum that makes a depth-on
RealSense two streams, the per-controller sum, and the block *verdict* — is single-
sourced from `backend.camera.bandwidth` and imported here, never restated. Two
sources of truth for that formula is the worst outcome for this WP, so this module
consumes `evaluate_bandwidth` rather than reproducing it.

What it adds is the WP-3B-02 behaviour the verdict alone does not carry:

- a `serial → bus` reconciliation that stamps each camera's controller from a parsed
  `lsusb -t` tree before the per-controller sum is taken (FR-CAM-005),
- the mitigation ladder attached to a blocked decision (FR-CAM-012/013), and
- `enforce_budget`, which turns a blocked decision into a refused save or start —
  a block, not a warning (FR-CAM-011).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from backend.camera.bandwidth import BandwidthVerdict, evaluate_bandwidth
from backend.camera.constants import USB3_EFFECTIVE_CAP_MBPS_REFERENCE
from backend.camera.descriptor import CameraDescriptor
from backend.sensing.bandwidth.constants import ACTION_START
from backend.sensing.bandwidth.mitigation import MitigationStep, mitigation_steps
from backend.sensing.bandwidth.topology import UsbTopology, assign_controllers


@dataclass(frozen=True)
class BudgetDecision:
    """A save/start decision for a camera configuration.

    Attributes:
        verdict: The imported block verdict (totals, per-controller sums, reasons).
        mitigations: The ladder offered when blocked; empty when the config passes.
    """

    verdict: BandwidthVerdict
    mitigations: tuple[MitigationStep, ...]

    @property
    def blocked(self) -> bool:
        """Whether save/start must be refused."""
        return self.verdict.blocked


class BandwidthBudgetError(RuntimeError):
    """A save or start was refused because the configuration exceeds the USB budget.

    Carries the blocked decision so a caller (or a UI) can surface both the breach
    reasons and the mitigation ladder without re-evaluating.
    """

    def __init__(self, action: str, decision: BudgetDecision) -> None:
        self.action = action
        self.decision = decision
        reasons = "; ".join(decision.verdict.reasons)
        super().__init__(f"{action} refused: USB bandwidth budget exceeded ({reasons})")


def evaluate_budget(
    descriptors: Sequence[CameraDescriptor],
    effective_cap_mbps: float = USB3_EFFECTIVE_CAP_MBPS_REFERENCE,
) -> BudgetDecision:
    """Render the budget decision for a set of enumerated cameras.

    Delegates the aggregate and per-controller comparison to the imported
    `evaluate_bandwidth`, then attaches the mitigation ladder when the verdict blocks.

    Args:
        descriptors: The cameras whose configuration is being decided, each with its
            `controller` already reflecting the physical bus.
        effective_cap_mbps: USB3 effective ceiling to compare against; a caller
            supplies it because the binding figure stays provisional until real
            cameras run `PG-CAM-001` (`02a` WP-0B-08 ⑨).

    Returns:
        (BudgetDecision) The block decision, with mitigations when blocked.
    """
    verdict = evaluate_bandwidth(descriptors, effective_cap_mbps)
    mitigations = mitigation_steps() if verdict.blocked else ()
    return BudgetDecision(verdict=verdict, mitigations=mitigations)


def evaluate_budget_with_topology(
    descriptors: Sequence[CameraDescriptor],
    topology: UsbTopology,
    serial_to_bus: Mapping[str, int],
    effective_cap_mbps: float = USB3_EFFECTIVE_CAP_MBPS_REFERENCE,
) -> BudgetDecision:
    """Reconcile controllers from a parsed `lsusb -t` tree, then decide the budget.

    The per-controller sum is only as correct as the controller each camera is
    assigned to; this stamps that assignment from the physical bus topology before
    deciding, so two cameras on one root hub are budgeted together (FR-CAM-005).

    Args:
        descriptors: The enumerated cameras.
        topology: The parsed USB topology.
        serial_to_bus: Each camera serial to its enumerated bus number.
        effective_cap_mbps: USB3 effective ceiling to compare against.

    Returns:
        (BudgetDecision) The block decision over the topology-reconciled cameras.
    """
    reconciled = assign_controllers(descriptors, topology, serial_to_bus)
    return evaluate_budget(reconciled, effective_cap_mbps)


def enforce_budget(
    descriptors: Sequence[CameraDescriptor],
    effective_cap_mbps: float = USB3_EFFECTIVE_CAP_MBPS_REFERENCE,
    action: str = ACTION_START,
) -> BudgetDecision:
    """Refuse a save or start when the configuration exceeds budget (FR-CAM-011).

    This is the block itself: an over-budget configuration raises rather than being
    allowed to proceed with a warning. A passing configuration returns its decision.

    Args:
        descriptors: The cameras whose configuration is being saved or started.
        effective_cap_mbps: USB3 effective ceiling to compare against.
        action: Which operation is being guarded (`save` or `start`), for the message.

    Returns:
        (BudgetDecision) The passing decision.

    Raises:
        BandwidthBudgetError: When the aggregate or any controller sum exceeds the cap.
    """
    decision = evaluate_budget(descriptors, effective_cap_mbps)
    if decision.blocked:
        raise BandwidthBudgetError(action, decision)
    return decision


__all__ = [
    "BandwidthBudgetError",
    "BudgetDecision",
    "enforce_budget",
    "evaluate_budget",
    "evaluate_budget_with_topology",
]
