"""Acceptance (1)/(5)/(3-fork): the plugin dist-name convention and the no-fork rule.

Light lane — no LeRobot import — so these run whether or not the robot stack is
installed. They pin the two static facts WP-1-01 owns about how OpenArm extends
LeRobot: the distribution name obeys the discovery convention, a name that does not
is refused, and the repository forks zero lines of LeRobot proper.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from contracts.plugin_api import convention
from registry.checks.corpus import Corpus

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_our_dist_name_is_convention_compliant() -> None:
    """Acceptance (1): our distribution name would be discovered by LeRobot."""
    assert convention.OPENARM_ROBOT_DIST == "lerobot_robot_openarm"
    assert convention.OPENARM_ROBOT_DIST.startswith(convention.ROBOT_PREFIX)
    assert convention.is_convention_compliant(convention.OPENARM_ROBOT_DIST)


def test_fr_sys_014_prefix_trio_is_covered() -> None:
    """The three names 01 FR-SYS-014 states are part of the scanned prefix set."""
    for prefix in (
        convention.ROBOT_PREFIX,
        convention.TELEOPERATOR_PREFIX,
        convention.CAMERA_PREFIX,
    ):
        assert prefix in convention.PLUGIN_DIST_PREFIXES


@pytest.mark.parametrize(
    "bad_name",
    [
        "openarm_follower",  # a LeRobot type name, not a distribution prefix
        "lerobot_openarm",  # missing the device-kind segment
        "robot_lerobot_openarm",  # prefix in the wrong place
        "openarm_lerobot_robot",  # convention token buried, not a prefix
    ],
)
def test_convention_violating_names_are_refused(bad_name: str) -> None:
    """Acceptance (5): a name outside the convention fails, with no silent success."""
    assert not convention.is_convention_compliant(bad_name)
    with pytest.raises(convention.PluginConventionError):
        convention.require_convention(bad_name)


def test_repository_forks_no_lerobot_source() -> None:
    """Acceptance (3): the repository adds zero lines to LeRobot proper (no fork)."""
    offenders = convention.forks_no_lerobot(Corpus(REPO_ROOT).tracked_files)
    assert offenders == (), f"repository forks LeRobot source at: {offenders}"
