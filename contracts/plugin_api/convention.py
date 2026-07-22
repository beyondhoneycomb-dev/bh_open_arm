"""The LeRobot third-party plugin distribution-name convention (01 FR-SYS-014).

A backend extends LeRobot only as a distribution whose name starts with one of the
prefixes `register_third_party_plugins()` scans (lerobot `utils/import_utils.py`);
a name outside the convention is never discovered, so a config it registers is
unreachable and the plugin silently does not exist. This module is the single
machine-readable statement of that convention plus two checks it grounds:

- a candidate distribution name obeys the prefix convention (acceptance (1)/(5)),
- the repository forks no LeRobot source at all — extension is additive, in a
  separate distribution, never a patched copy of LeRobot's tree (01 FR-SYS-003).

Pure stdlib: no LeRobot import, so the convention checks run in the light lane.
"""

from __future__ import annotations

# The exact prefix set `register_third_party_plugins()` scans (import_utils.py). A
# distribution whose Name starts with one of these is imported for its
# `@register_subclass` side effects; anything else is never discovered. The three
# 01 FR-SYS-014 names it, robot / teleoperator / camera, and the two LeRobot also
# scans, are both kept so a test can bind this tuple back to the live mechanism.
ROBOT_PREFIX = "lerobot_robot_"
TELEOPERATOR_PREFIX = "lerobot_teleoperator_"
CAMERA_PREFIX = "lerobot_camera_"
PLUGIN_DIST_PREFIXES = (
    ROBOT_PREFIX,
    CAMERA_PREFIX,
    TELEOPERATOR_PREFIX,
    "lerobot_policy_",
    "lerobot_env_",
)

# The OpenArm follower plugin's distribution and top-level module name.
OPENARM_ROBOT_DIST = "lerobot_robot_openarm"

# Path prefixes a forked/vendored copy of LeRobot's own package tree would occupy.
# Our repository must contain none of these: extension is a separate distribution,
# never an edited copy of LeRobot proper (01 FR-SYS-003).
LEROBOT_FORK_PREFIXES = ("lerobot/", "src/lerobot/")


class PluginConventionError(ValueError):
    """Raised when a distribution name violates the third-party plugin convention."""


def is_convention_compliant(dist_name: str) -> bool:
    """Report whether a distribution name would be discovered by LeRobot.

    Args:
        dist_name: Candidate distribution/module name.

    Returns:
        (bool) True when the name starts with a scanned plugin prefix.
    """
    return dist_name.startswith(PLUGIN_DIST_PREFIXES)


def require_convention(dist_name: str) -> None:
    """Reject a distribution name outside the third-party plugin convention.

    Args:
        dist_name: Candidate distribution/module name.

    Raises:
        PluginConventionError: When the name would never be discovered, so the
            registration it performs would silently never happen (acceptance (5)).
    """
    if not is_convention_compliant(dist_name):
        raise PluginConventionError(
            f"distribution name {dist_name!r} matches none of {PLUGIN_DIST_PREFIXES}; "
            "register_third_party_plugins() would never import it, so its "
            "@register_subclass never runs and the plugin is unreachable"
        )


def forks_no_lerobot(tracked_files: tuple[str, ...]) -> tuple[str, ...]:
    """Return any tracked file that forks LeRobot's own package tree.

    Args:
        tracked_files: Root-relative POSIX paths under version control.

    Returns:
        (tuple[str, ...]) Offending paths, sorted; empty means the repository
            adds zero lines to LeRobot proper (01 FR-SYS-003, acceptance (3)).
    """
    return tuple(sorted(path for path in tracked_files if path.startswith(LEROBOT_FORK_PREFIXES)))
