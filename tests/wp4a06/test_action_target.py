"""CG-4A-06c — zero paths where `.vel`/`.torque` enters the action target.

`02c` §1.6 ③ (`10` FR-TRN-066/074, `11` FR-INF-074, triple canonical). Two halves,
both proven here:

- static: the AST scan finds no torque-into-action-target construction in this
  package (`scan_package` is empty), and a positive control proves the scan bites;
- runtime: `select_action_target_indices` refuses a poisoned action-name set and
  the paired experiment's arms carry a position-only action target.
"""

from __future__ import annotations

import pytest

from backend.training.projection import (
    ACTION_TARGET_FORBIDDEN_SUFFIXES,
    ActionTargetLeakError,
    ProjectionKind,
    generate_paired_experiment,
    scan_package,
    scan_source,
    select_action_target_indices,
)
from contracts.recorder import action_names
from tests.wp4a06.fixtures import (
    CLEAN_SOURCE,
    LEAK_SOURCE,
    arm_request,
    observation_config,
)


def test_package_has_no_action_target_torque_leak() -> None:
    """No source in this WP lets a torque flow into an action-target constructor."""
    assert scan_package() == ()


def test_static_scan_bites_on_positive_control() -> None:
    """The scan flags a torque handed to an action target — it is not vacuous."""
    findings = scan_source(LEAK_SOURCE, module="fixture.leak")
    assert findings
    assert all(finding.rule == "torque-in-action-target" for finding in findings)


def test_static_scan_clean_on_position_only_control() -> None:
    """A position-only action-target construction produces no finding."""
    assert scan_source(CLEAN_SOURCE, module="fixture.clean") == ()


def test_poisoned_action_names_are_refused() -> None:
    """A `.vel`/`.torque` channel in the action names raises before any index is returned."""
    targets = action_names(bimanual=True)
    for suffix in ACTION_TARGET_FORBIDDEN_SUFFIXES:
        with pytest.raises(ActionTargetLeakError):
            select_action_target_indices([*targets, f"left_joint_1{suffix}"])


def test_clean_action_names_select_only_pos() -> None:
    """A canonical action name list selects all channels, none of them non-position."""
    targets = action_names(bimanual=True)
    indices = select_action_target_indices(targets)
    assert indices == list(range(len(targets)))
    for index in indices:
        assert not targets[index].endswith(ACTION_TARGET_FORBIDDEN_SUFFIXES)


def test_both_arms_carry_position_only_action_target() -> None:
    """Neither the FULL nor the POS_ONLY arm has a `.vel`/`.torque` action channel."""
    config = observation_config()
    experiment = generate_paired_experiment(
        arm_request(ProjectionKind.FULL), arm_request(ProjectionKind.POS_ONLY), config
    )
    for arm in (experiment.arm_a, experiment.arm_b):
        assert arm.action_names
        for name in arm.action_names:
            assert not name.endswith(ACTION_TARGET_FORBIDDEN_SUFFIXES)
