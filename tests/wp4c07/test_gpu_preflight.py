"""CG-4C-07d — GPU preflight: Cosmos Reason 2 (Hopper/Blackwell) vs the owned fleet.

`FR-SIM-095`: the evaluation critic runs only on a Hopper- or Blackwell-class GPU. The
preflight cross-checks that against the committed `DeploymentTarget` fleet and renders
a verdict per target: RTX 5090 (Blackwell) eligible, RTX A6000 (Ampere) not. The test
checks both named cases, that every fleet target gets a verdict (per-target render),
and that the eligibility set is exactly the RTX 5090 for this fleet.
"""

from __future__ import annotations

from backend.compat.deploy_matrix.target import DeploymentTarget
from backend.eval.autojudge import (
    eligible_targets,
    fleet_has_eligible_target,
    preflight_fleet,
    preflight_target,
)
from backend.eval.autojudge.constants import ARCH_AMPERE, ARCH_BLACKWELL


def test_rtx_5090_is_eligible() -> None:
    """RTX 5090 is Blackwell -> eligible for Cosmos Reason 2."""
    result = preflight_target(DeploymentTarget.RTX_5090)
    assert result.architecture == ARCH_BLACKWELL
    assert result.eligible is True


def test_rtx_a6000_is_not_eligible() -> None:
    """RTX A6000 is Ampere -> ineligible; the reason names the required architectures."""
    result = preflight_target(DeploymentTarget.RTX_A6000)
    assert result.architecture == ARCH_AMPERE
    assert result.eligible is False
    assert "hopper" in result.reason and ARCH_BLACKWELL in result.reason


def test_every_fleet_target_gets_a_verdict() -> None:
    """The preflight renders one verdict per owned target (per-target render)."""
    fleet = preflight_fleet()
    assert {result.target for result in fleet} == set(DeploymentTarget)
    assert len(fleet) == len(list(DeploymentTarget))


def test_only_rtx_5090_is_eligible_in_this_fleet() -> None:
    """Of the four owned targets, only the RTX 5090 clears Cosmos Reason 2."""
    assert eligible_targets() == (DeploymentTarget.RTX_5090,)
    assert fleet_has_eligible_target() is True


def test_jetson_targets_are_ineligible() -> None:
    """Both Jetson targets are Ampere-class and therefore ineligible."""
    for target in (DeploymentTarget.JETSON_NANO, DeploymentTarget.JETSON_ORIN):
        assert preflight_target(target).eligible is False
