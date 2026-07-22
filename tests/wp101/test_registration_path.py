"""Acceptance (2)/(4): registration via the third-party path, and factory resolution.

Robot lane — skipped when LeRobot is absent (mirrors tests/wp0c02). Drives the exact
mechanism a deployed plugin uses: importing the distribution runs
`@register_subclass`, and `make_robot_from_config` resolves a non-hardcoded config
through its `else` fallback into our package. No LeRobot source is edited.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

pytest.importorskip("lerobot")

from lerobot.utils.import_utils import register_third_party_plugins  # noqa: E402

from contracts.plugin_api import convention, extension  # noqa: E402
from packages.lerobot_robot_openarm import (  # noqa: E402
    BI_OA_FOLLOWER_TYPE,
    OA_FOLLOWER_TYPE,
    PROBE_TYPE,
    OpenArmPluginProbe,
    OpenArmPluginProbeConfig,
)


def test_importing_the_plugin_registers_its_choices() -> None:
    """Acceptance (2): the import side effect registers our config choices."""
    registered = extension.registered_choice_names()
    assert {OA_FOLLOWER_TYPE, BI_OA_FOLLOWER_TYPE, PROBE_TYPE} <= registered


def test_convention_prefixes_match_the_live_discovery_mechanism() -> None:
    """Our prefix tuple is exactly what `register_third_party_plugins` scans for."""
    source = inspect.getsource(register_third_party_plugins)
    for prefix in convention.PLUGIN_DIST_PREFIXES:
        assert f'"{prefix}"' in source, f"{prefix} is not scanned by the live mechanism"


def test_discovery_entry_point_runs() -> None:
    """`register_third_party_plugins()` is callable and completes without error."""
    register_third_party_plugins()


def test_make_robot_from_config_fallback_resolves_our_plugin(tmp_path: Path) -> None:
    """Acceptance (4): the factory fallback instantiates our plugin's backend."""
    assert extension.fallback_reaches_make_device()
    robot = extension.resolve(OpenArmPluginProbeConfig(calibration_dir=tmp_path))
    assert isinstance(robot, OpenArmPluginProbe)
    assert robot.robot_type == PROBE_TYPE


def test_probe_type_is_not_a_hardcoded_branch() -> None:
    """The probe reaches the fallback because its type is not a hardcoded name."""
    assert PROBE_TYPE not in extension.make_robot_from_config_source()
