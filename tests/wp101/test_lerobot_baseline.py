"""Acceptance (2)/(3): LeRobot proper is unedited — 0 lines vs the pinned SHA.

Robot lane — skipped when LeRobot is absent. Verifies against the installed pinned
release (deps/lerobot.pin): the installed version equals the pin's resolved version
(the offline tie to the pinned SHA), the hardcoded OpenArm branch is present and
unedited (16 D-1), the factory still falls through to the third-party resolver, and
none of our plugin types was injected as a hardcoded branch (01 FR-SYS-003).
"""

from __future__ import annotations

import pytest

pytest.importorskip("lerobot")

from contracts.plugin_api import extension  # noqa: E402
from packages.lerobot_robot_openarm import (  # noqa: E402
    BI_OA_FOLLOWER_TYPE,
    OA_FOLLOWER_TYPE,
    PROBE_TYPE,
)
from registry.env.upstream import make_robot_from_config_hardcoded_openarm  # noqa: E402


def test_installed_lerobot_matches_the_pin() -> None:
    """Acceptance (3): the installed release carries the pinned resolved version."""
    assert extension.installed_matches_pin(), (
        f"installed lerobot {extension.installed_lerobot_version()} "
        "does not match deps/lerobot.pin resolved_version"
    )


def test_hardcoded_openarm_branch_present_and_intact() -> None:
    """16 D-1: LeRobot's built-in OpenArm branch is present and unedited."""
    assert extension.hardcoded_openarm_branch_present()
    # Reuse the WP-ENV-04 upstream predicate that also asserts the branch's classes.
    assert make_robot_from_config_hardcoded_openarm().ok


def test_factory_still_falls_through_to_third_party_resolver() -> None:
    """Acceptance (2)/(4): the else-branch reaches make_device_from_device_class."""
    assert extension.fallback_reaches_make_device()


def test_no_plugin_type_was_injected_as_a_hardcoded_branch() -> None:
    """Acceptance (2): 0 hardcoded-branch edits — none of our types is in the factory."""
    injected = extension.types_not_injected((OA_FOLLOWER_TYPE, BI_OA_FOLLOWER_TYPE, PROBE_TYPE))
    assert injected == (), f"plugin types were added as hardcoded branches: {injected}"
