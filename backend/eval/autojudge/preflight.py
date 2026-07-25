"""GPU preflight for Cosmos Reason 2 — Hopper/Blackwell against the owned fleet.

`FR-SIM-095`: the evaluation critic (Cosmos Reason 2) runs only on a Hopper- or
Blackwell-class GPU. `02c` §3.7 CG-4C-07d makes the check concrete: cross-check that
requirement against the OWNED fleet and render a verdict per target — RTX 5090
(Blackwell) eligible, RTX A6000 (Ampere) not.

The fleet is not re-invented here: it is the committed `DeploymentTarget` enum
(WP-4B-04, `02c` §2.4), the same four ids the environment layer owns. Importing it
keeps this preflight from becoming a second, drifting list of GPUs — it maps each
canonical target to its GPU architecture generation and applies the one eligibility
rule. If the fleet gains a target, this map must gain a row (a missing row raises
rather than silently passing), so the cross-check cannot go stale unnoticed.
"""

from __future__ import annotations

from dataclasses import dataclass

# WP-4B-04 fleet consumption: the owned deployment fleet is the committed
# `DeploymentTarget`, imported (never redefined) so "the owned fleet" means exactly
# one thing across the codebase. Imported from the submodule (enum-only, no sim/robot
# stack) so this preflight stays importable offline.
from backend.compat.deploy_matrix.target import DeploymentTarget
from backend.eval.autojudge.constants import (
    ARCH_AMPERE,
    ARCH_BLACKWELL,
    ARCH_HOPPER,
    COSMOS_REASON_2,
)

# The GPU architecture generation of each fleet target. Jetson Orin/Orin Nano and the
# RTX A6000 are Ampere; the RTX 5090 is Blackwell. Cosmos Reason 2 needs Hopper or
# Blackwell, so of the owned fleet only the RTX 5090 clears it. This is a factual map
# of the fleet, kept complete against `DeploymentTarget` by `_require_complete`.
_TARGET_ARCH: dict[DeploymentTarget, str] = {
    DeploymentTarget.JETSON_NANO: ARCH_AMPERE,
    DeploymentTarget.JETSON_ORIN: ARCH_AMPERE,
    DeploymentTarget.RTX_5090: ARCH_BLACKWELL,
    DeploymentTarget.RTX_A6000: ARCH_AMPERE,
}

# The architecture generations Cosmos Reason 2 accepts (`FR-SIM-095`: Hopper/Blackwell).
# Hopper is not a fleet target but is listed so the eligibility rule states the model's
# real requirement, not merely "is it the 5090".
_COSMOS_ELIGIBLE_ARCHS: frozenset[str] = frozenset({ARCH_HOPPER, ARCH_BLACKWELL})


def _require_complete() -> None:
    """Refuse a fleet target with no architecture row (keeps the cross-check honest)."""
    missing = set(DeploymentTarget) - set(_TARGET_ARCH)
    if missing:
        raise RuntimeError(
            "GPU preflight is missing an architecture row for fleet target(s): "
            f"{sorted(t.value for t in missing)}"
        )


_require_complete()


@dataclass(frozen=True)
class GpuPreflightResult:
    """The Cosmos Reason 2 eligibility verdict for one fleet target (CG-4C-07d).

    Attributes:
        target: The deployment target evaluated.
        architecture: Its GPU architecture generation.
        eligible: Whether Cosmos Reason 2 can run on it (arch is Hopper/Blackwell).
        reason: Why — naming the required architectures when ineligible.
    """

    target: DeploymentTarget
    architecture: str
    eligible: bool
    reason: str


def preflight_target(target: DeploymentTarget) -> GpuPreflightResult:
    """Render the Cosmos Reason 2 eligibility verdict for one target.

    Args:
        target: The fleet target to evaluate.

    Returns:
        (GpuPreflightResult) Its architecture and eligibility.
    """
    architecture = _TARGET_ARCH[target]
    eligible = architecture in _COSMOS_ELIGIBLE_ARCHS
    if eligible:
        reason = f"{COSMOS_REASON_2} runs on {architecture}-class GPUs"
    else:
        required = ", ".join(sorted(_COSMOS_ELIGIBLE_ARCHS))
        reason = f"{COSMOS_REASON_2} requires a {required} GPU; {target.value} is {architecture}"
    return GpuPreflightResult(
        target=target,
        architecture=architecture,
        eligible=eligible,
        reason=reason,
    )


def preflight_fleet() -> tuple[GpuPreflightResult, ...]:
    """Render the Cosmos Reason 2 eligibility verdict for every owned target.

    Returns:
        (tuple[GpuPreflightResult, ...]) One verdict per `DeploymentTarget`, in enum
            order — the per-target render CG-4C-07d requires.
    """
    return tuple(preflight_target(target) for target in DeploymentTarget)


def eligible_targets() -> tuple[DeploymentTarget, ...]:
    """Return the fleet targets Cosmos Reason 2 can run on.

    Returns:
        (tuple[DeploymentTarget, ...]) The eligible targets (RTX 5090 for this fleet).
    """
    return tuple(result.target for result in preflight_fleet() if result.eligible)


def fleet_has_eligible_target() -> bool:
    """Whether any owned target can run Cosmos Reason 2.

    When this is False the whole fleet is ineligible, and `02c` §3.7 음성 분기 ④ makes
    that a wave-rebalancing question (the optional WP becomes unnecessary), not a gate
    state — 4C still completes on human labels.

    Returns:
        (bool) True when at least one target is eligible.
    """
    return bool(eligible_targets())
