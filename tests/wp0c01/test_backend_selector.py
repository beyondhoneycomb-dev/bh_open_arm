"""Acceptance ④⑤ -- the selector defaults to MuJoCo and never downgrades silently.

The default request resolves to MuJoCo (`09` FR-SIM-102, stage-1 canonical). An
Isaac request that cannot be met is auto-downgraded to MuJoCo with the reason
recorded; a `BackendSelection` cannot represent a downgrade without a reason.
"""

from __future__ import annotations

import pytest

from packages.lerobot_robot_openarm_mujoco import (
    Backend,
    BackendSelection,
    IsaacAvailability,
    select_backend,
)

pytest.importorskip("mujoco")

_ISAAC_UNAVAILABLE = IsaacAvailability(available=False, reason="no CUDA GPU / isaacsim absent")
_ISAAC_AVAILABLE = IsaacAvailability(available=True, reason="")


def test_default_selection_is_mujoco() -> None:
    selection = select_backend()
    assert selection.backend is Backend.MUJOCO
    assert selection.requested is Backend.MUJOCO
    assert selection.downgraded is False
    assert selection.version  # backend/version recorded (09 FR-SIM-102)


def test_isaac_unavailable_downgrades_to_mujoco_with_reason() -> None:
    selection = select_backend(Backend.ISAAC, isaac_probe=lambda: _ISAAC_UNAVAILABLE)
    assert selection.backend is Backend.MUJOCO
    assert selection.requested is Backend.ISAAC
    assert selection.downgraded is True
    assert _ISAAC_UNAVAILABLE.reason in selection.reason
    assert selection.version  # the MuJoCo it fell back to is recorded


def test_real_isaac_probe_downgrades_here() -> None:
    # Isaac Sim is not installed in this environment, so a real Isaac request must
    # downgrade rather than fail -- and it must say why (no silent downgrade).
    selection = select_backend(Backend.ISAAC)
    assert selection.backend is Backend.MUJOCO
    assert selection.downgraded is True
    assert selection.reason.strip()


def test_isaac_available_is_honoured_without_downgrade() -> None:
    selection = select_backend(
        Backend.ISAAC,
        isaac_probe=lambda: _ISAAC_AVAILABLE,
        isaac_version_probe=lambda: "isaacsim 4.0",
    )
    assert selection.backend is Backend.ISAAC
    assert selection.downgraded is False
    assert selection.version == "isaacsim 4.0"


def test_downgrade_without_reason_is_unrepresentable() -> None:
    with pytest.raises(ValueError, match="reason"):
        BackendSelection(
            backend=Backend.MUJOCO,
            version="mujoco 3.10",
            requested=Backend.ISAAC,
            downgraded=True,
            reason="",
        )


def test_downgrade_to_same_backend_is_rejected() -> None:
    with pytest.raises(ValueError, match="other than the requested"):
        BackendSelection(
            backend=Backend.MUJOCO,
            version="mujoco 3.10",
            requested=Backend.MUJOCO,
            downgraded=True,
            reason="cannot downgrade to self",
        )


def test_non_downgrade_must_return_requested_backend() -> None:
    with pytest.raises(ValueError, match="return the requested backend"):
        BackendSelection(
            backend=Backend.MUJOCO,
            version="mujoco 3.10",
            requested=Backend.ISAAC,
            downgraded=False,
            reason="",
        )
