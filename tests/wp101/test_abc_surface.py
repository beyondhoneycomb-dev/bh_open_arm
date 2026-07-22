"""The frozen CTR-PLUG@v1 Robot ABC surface (09 FR-SIM-097).

Robot lane — skipped when LeRobot is absent. Pins the shared ABC surface WP-1-01
re-confirms: every backend implements the same LeRobot Robot method set, the
observation/action feature contract is frozen at the ABC (subclasses cannot
redeclare it), and its widths are the frozen 49 (48 + drop counter) and 16.
"""

from __future__ import annotations

import pytest

pytest.importorskip("lerobot")

from contracts.plugin.robot_abc import OpenArmRobot  # noqa: E402
from contracts.plugin_api import surface  # noqa: E402


def test_backend_must_implement_the_open_abc_methods() -> None:
    """A backend still owns connect/observe/act and the connection flags."""
    assert surface.backend_must_implement() == {
        "connect",
        "disconnect",
        "calibrate",
        "configure",
        "get_observation",
        "send_action",
        "is_connected",
        "is_calibrated",
    }


def test_feature_contract_is_frozen_at_the_abc() -> None:
    """The observation/action feature dicts are fixed by OpenArmRobot, not subclasses."""
    assert surface.features_fixed_by_openarm() == {"observation_features", "action_features"}
    assert "observation_features" not in OpenArmRobot.__abstractmethods__
    assert "action_features" not in OpenArmRobot.__abstractmethods__


def test_frozen_channel_widths() -> None:
    """The frozen schema is 49 observation channels (48 + drop counter) and 16 actions."""
    assert surface.observation_width(bimanual=True) == surface.FROZEN_OBSERVATION_WIDTH == 49
    assert surface.action_width(bimanual=True) == surface.FROZEN_ACTION_WIDTH == 16


def test_frozen_abc_methods_cover_the_open_and_fixed_sets() -> None:
    """Every Robot ABC member is either fixed by OpenArmRobot or left to the backend."""
    assert surface.frozen_abc_methods() == (
        surface.features_fixed_by_openarm() | surface.backend_must_implement()
    )
