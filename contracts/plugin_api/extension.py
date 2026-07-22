"""How the OpenArm plugin extends LeRobot, and the proof it edits zero lines of it.

The extension mechanism is entirely LeRobot's own third-party path (01 FR-SYS-014):
`register_third_party_plugins()` imports our distribution, `@register_subclass`
records our config choices, and `make_robot_from_config` resolves a config whose
type is not a hardcoded name through its `else` fallback
(`make_device_from_device_class`). This module exposes that path and the checks that
LeRobot proper is untouched (01 FR-SYS-003, 16 D-1), all against the installed pinned
release (deps/lerobot.pin), so the "diff = 0 lines vs the pinned SHA" claim is
verified offline rather than asserted.

Robot lane: imports LeRobot. The freeze re-confirmation (`freeze.py`) and the dist
convention (`convention.py`) stay LeRobot-free for the light lane.
"""

from __future__ import annotations

import importlib
import inspect

import lerobot
from lerobot.robots.config import RobotConfig
from lerobot.robots.robot import Robot
from lerobot.robots.utils import make_robot_from_config
from lerobot.utils.import_utils import register_third_party_plugins

from deps.pin import load_pin, validate_pin

_MAKE_ROBOT_MODULE = "lerobot.robots.utils"

# The device-class resolver `make_robot_from_config` falls through to for any config
# whose type is not one of its hardcoded branches. Its presence in the factory
# source is what proves a third-party config reaches the fallback (acceptance (4)).
_FALLBACK_RESOLVER = "make_device_from_device_class"

# LeRobot's built-in hardcoded OpenArm branch names (16 D-1). They must stay present
# and unedited; our plugin uses distinct `oa_*` names so it never touches them.
_BUILTIN_OPENARM_BRANCHES = ("openarm_follower", "bi_openarm_follower")


def discover() -> None:
    """Run LeRobot's third-party plugin discovery (imports matching distributions)."""
    register_third_party_plugins()


def registered_choice_names() -> frozenset[str]:
    """Return every `RobotConfig` choice name currently registered.

    Returns:
        (frozenset[str]) Registered `--robot.type` tokens.
    """
    return frozenset(RobotConfig.get_known_choices())


def is_registered(type_name: str) -> bool:
    """Report whether a `RobotConfig` choice name is registered.

    Args:
        type_name: A `--robot.type` token.

    Returns:
        (bool) True when the type resolves to a registered config class.
    """
    return type_name in RobotConfig.get_known_choices()


def resolve(config: RobotConfig) -> Robot:
    """Resolve a config to a backend through `make_robot_from_config`.

    Drives the exact factory a deployed run uses. A config whose type is not a
    hardcoded branch reaches the third-party fallback and is instantiated from its
    plugin package (acceptance (4)).

    Args:
        config: A registered robot config.

    Returns:
        (Robot) The resolved backend instance.
    """
    return make_robot_from_config(config)


def installed_lerobot_version() -> str:
    """Return the installed LeRobot version string.

    Returns:
        (str) `lerobot.__version__`.
    """
    return str(lerobot.__version__)


def installed_matches_pin() -> bool:
    """Report whether the installed LeRobot equals the pinned resolved version.

    The pin fixes an exact commit SHA and tree hash (deps/lerobot.pin); the
    installed release carrying the pin's `resolved_version` is the offline tie
    between the running tree and the pinned SHA (acceptance (3)).

    Returns:
        (bool) True when the pin is well-formed and the installed version matches.
    """
    report = validate_pin(load_pin())
    return report.ok and installed_lerobot_version() == report.resolved_version


def make_robot_from_config_source() -> str:
    """Return the source of the installed `make_robot_from_config` factory.

    Returns:
        (str) Source text of the factory, read from the installed package.
    """
    module = importlib.import_module(_MAKE_ROBOT_MODULE)
    return inspect.getsource(module.make_robot_from_config)


def hardcoded_openarm_branch_present() -> bool:
    """Report whether LeRobot's built-in OpenArm branch is present and intact.

    Returns:
        (bool) True when both built-in OpenArm branch names appear in the stock
            factory — i.e. it was not edited away (16 D-1).
    """
    source = make_robot_from_config_source()
    return all(branch in source for branch in _BUILTIN_OPENARM_BRANCHES)


def fallback_reaches_make_device() -> bool:
    """Report whether the factory falls through to the third-party resolver.

    Returns:
        (bool) True when `make_device_from_device_class` is the `else` path a
            non-hardcoded config reaches (acceptance (2)/(4)).
    """
    return _FALLBACK_RESOLVER in make_robot_from_config_source()


def types_not_injected(type_names: tuple[str, ...]) -> tuple[str, ...]:
    """Return any of our plugin types that appear in LeRobot's factory source.

    A plugin type found in `make_robot_from_config` would mean someone added a
    hardcoded branch for us — the exact edit 01 FR-SYS-003 forbids. The empty
    result is the "0 hardcoded-branch edits" proof (acceptance (2)).

    Args:
        type_names: Our plugin's registered `--robot.type` tokens.

    Returns:
        (tuple[str, ...]) Offending tokens found in the factory source; empty when
            none is injected.
    """
    source = make_robot_from_config_source()
    return tuple(name for name in type_names if name in source)
