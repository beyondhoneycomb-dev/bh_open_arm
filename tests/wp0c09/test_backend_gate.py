"""Acceptance ⑪/⑫/⑬ — MuJoCo is the canonical hard gate, never Isaac."""

from __future__ import annotations

import pytest

from packages.lerobot_robot_openarm_mujoco.backend_selector import (
    Backend,
    BackendSelection,
)
from sim.dryrun.backend_gate import (
    CrossBackendTransplantError,
    DomainRandomizationCenter,
    HardGate,
    IsaacHardGateError,
    designate_hard_gate,
    guard_dr_center_transplant,
)


def test_default_hard_gate_is_mujoco() -> None:
    """⑪ The default gate resolves to the canonical MuJoCo backend."""
    gate = designate_hard_gate()
    assert gate.backend is Backend.MUJOCO


def test_isaac_request_auto_downgrades_with_a_reason() -> None:
    """⑪ An unmet Isaac request downgrades to MuJoCo, reason recorded (no silent)."""
    gate = designate_hard_gate(Backend.ISAAC)
    assert gate.backend is Backend.MUJOCO
    assert gate.selection.downgraded is True
    assert gate.selection.reason


def test_isaac_as_hard_gate_is_rejected() -> None:
    """⑫ Designating Isaac as the final hard gate is refused (FR-SIM-135)."""
    isaac_selection = BackendSelection(
        backend=Backend.ISAAC,
        version="isaacsim 5.1.0",
        requested=Backend.ISAAC,
        downgraded=False,
        reason="",
    )
    with pytest.raises(IsaacHardGateError):
        HardGate(selection=isaac_selection)


def test_cross_backend_dr_center_transplant_is_rejected() -> None:
    """⑬ A DR centre identified on Isaac cannot be used on a MuJoCo run (FR-SIM-092)."""
    center = DomainRandomizationCenter(
        parameter="joint7_armature", value=0.01, source_backend=Backend.ISAAC
    )
    with pytest.raises(CrossBackendTransplantError):
        guard_dr_center_transplant(center, run_backend=Backend.MUJOCO)


def test_same_backend_dr_center_is_allowed() -> None:
    """⑬ A DR centre identified on the run's own backend transplants cleanly."""
    center = DomainRandomizationCenter(
        parameter="joint7_armature", value=0.01, source_backend=Backend.MUJOCO
    )
    guard_dr_center_transplant(center, run_backend=Backend.MUJOCO)
