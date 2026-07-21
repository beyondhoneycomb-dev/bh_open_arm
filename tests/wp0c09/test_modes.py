"""Acceptance ①(runtime) and ⑭ — the mode tier is exclusive and CAN-less."""

from __future__ import annotations

import pytest

from packages.lerobot_robot_openarm_mujoco.can_guard import SimModeCanError, assert_no_can_open
from sim.dryrun.modes import (
    ModeController,
    ModeExclusionError,
    SimMode,
    validate_active_modes,
)


def test_two_modes_active_is_a_violation() -> None:
    """⑭ A fixture claiming two active modes is rejected."""
    with pytest.raises(ModeExclusionError):
        validate_active_modes({SimMode.PURE_SIM, SimMode.DRY_RUN})


def test_single_and_empty_active_sets_are_legal() -> None:
    """⑭ At most one active mode is legal; zero is legal too."""
    validate_active_modes(set())
    validate_active_modes({SimMode.DIGITAL_TWIN})


def test_controller_refuses_a_second_concurrent_mode() -> None:
    """⑭ Activating a second mode while one is active is refused."""
    controller = ModeController()
    controller.activate(SimMode.PURE_SIM)
    assert controller.active is SimMode.PURE_SIM
    with pytest.raises(ModeExclusionError):
        controller.activate(SimMode.DRY_RUN)


def test_controller_allows_reactivating_the_same_mode() -> None:
    """Re-activating the already-active mode is a no-op, not a violation."""
    controller = ModeController()
    controller.activate(SimMode.DRY_RUN)
    controller.activate(SimMode.DRY_RUN)
    assert controller.active is SimMode.DRY_RUN


def test_deactivate_returns_the_tier_to_idle() -> None:
    """After deactivation another mode may be activated."""
    controller = ModeController()
    controller.activate(SimMode.PURE_SIM)
    controller.deactivate()
    controller.activate(SimMode.DIGITAL_TWIN)
    assert controller.active is SimMode.DIGITAL_TWIN


def test_activation_passes_the_zero_can_open_runtime_hook() -> None:
    """① Each mode activation re-checks the zero-CAN-open invariant."""
    controller = ModeController()
    controller.activate(SimMode.DIGITAL_TWIN)  # would raise if the CAN hook tripped


def test_can_open_hook_bites_on_a_nonzero_count() -> None:
    """① The runtime hook the controller uses is not vacuous."""
    assert_no_can_open(0)
    with pytest.raises(SimModeCanError):
        assert_no_can_open(1)
