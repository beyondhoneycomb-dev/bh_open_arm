"""The target recognizer refuses non-members and stays in sync with the ENV fleet.

`02c` §2.4 enumerates exactly four deployment targets and excludes A100/H100 by name
(§5.1 / §6.1). The recognizer must resolve the four and refuse the rest — an unknown id
and, distinctly, an explicit datacenter-GPU exclusion — because a silently-accepted fifth
target would bypass every per-target gate. `crosscheck_fleet_matrix` proves the enum has
not drifted from `targets.matrix` (WP-ENV-02), the fleet's data owner.
"""

from __future__ import annotations

import pytest

from backend.compat.deploy_matrix.target import (
    DeploymentTarget,
    TargetClass,
    UnsupportedTargetError,
    crosscheck_fleet_matrix,
    recognize_target,
    target_class,
)


def test_recognizes_every_fleet_target() -> None:
    """Each canonical fleet id round-trips to its enum member."""
    for target in DeploymentTarget:
        assert recognize_target(target.value) is target


def test_recognizes_case_insensitively() -> None:
    """An id with stray case/whitespace still resolves — the fleet ids are lowercase."""
    assert recognize_target("  Jetson_Orin ") is DeploymentTarget.JETSON_ORIN


def test_excluded_datacenter_gpus_are_refused_as_exclusions() -> None:
    """A100/H100 are refused, flagged as explicit SPINE §7 exclusions, not unknowns."""
    for name in ("a100", "h100", "H100"):
        with pytest.raises(UnsupportedTargetError) as excinfo:
            recognize_target(name)
        assert excinfo.value.excluded is True


def test_unknown_target_is_refused_as_unknown() -> None:
    """An id outside both the fleet and the exclusion set is refused as unknown."""
    with pytest.raises(UnsupportedTargetError) as excinfo:
        recognize_target("agx_thor")
    assert excinfo.value.excluded is False


def test_target_class_splits_jetson_from_rtx() -> None:
    """The conservative-default regimes are Jetson (edge) vs RTX (workstation)."""
    assert target_class(DeploymentTarget.JETSON_NANO) is TargetClass.JETSON
    assert target_class(DeploymentTarget.JETSON_ORIN) is TargetClass.JETSON
    assert target_class(DeploymentTarget.RTX_5090) is TargetClass.RTX
    assert target_class(DeploymentTarget.RTX_A6000) is TargetClass.RTX


def test_enum_agrees_with_env_fleet_matrix() -> None:
    """The enum has not drifted from `targets.matrix` FLEET/EXCLUDED (WP-ENV-02)."""
    assert crosscheck_fleet_matrix() == ()
