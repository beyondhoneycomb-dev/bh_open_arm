"""Static pre-merge lints for two SPINE §5 I-7 / plugin invariants (acceptance ③ ④).

Pure predicates over declared configuration, so the light lane runs them without the
robot stack, and the fixtures that must fail live in `tests/env03`.

  ③ `push_to_hub=true` is refused. `14` FR-OPS-082 forces the default False with an
    explicit opt-in; a config that turns it on without the audited opt-in leaks
    in-house data to the Hub (`16` §11 #3).
  ④ A LeRobot third-party plugin distribution name must match one of the reserved
    prefixes (`01` FR-SYS-014): `lerobot_robot_*`, `lerobot_teleoperator_*`,
    `lerobot_camera_*`. Anything else is not discoverable by the plugin mechanism.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

PUSH_TO_HUB_KEY = "push_to_hub"
AUDITED_OPT_IN_KEY = "push_to_hub_opt_in_audited"

PLUGIN_PREFIXES = ("lerobot_robot_", "lerobot_teleoperator_", "lerobot_camera_")
_PLUGIN_NAME = re.compile(r"^(?:lerobot_robot_|lerobot_teleoperator_|lerobot_camera_)[a-z0-9_]+$")


@dataclass(frozen=True)
class LintResult:
    """The outcome of one pre-merge lint.

    Attributes:
        ok: True when the input is accepted.
        reason: Why it was refused; empty when accepted.
    """

    ok: bool
    reason: str


def check_push_to_hub(config: dict[str, object]) -> LintResult:
    """Refuse a config that enables `push_to_hub` without the audited opt-in.

    Args:
        config: A dataset/record config mapping.

    Returns:
        (LintResult) Refused when push_to_hub is true and the opt-in is not audited.
    """
    enabled = bool(config.get(PUSH_TO_HUB_KEY, False))
    audited = bool(config.get(AUDITED_OPT_IN_KEY, False))
    if enabled and not audited:
        return LintResult(
            ok=False,
            reason="push_to_hub=true without an audited opt-in (FR-OPS-082): in-house data leaks",
        )
    return LintResult(ok=True, reason="")


def check_plugin_name(dist_name: str) -> LintResult:
    """Refuse a plugin distribution name outside the reserved LeRobot prefixes.

    Args:
        dist_name: A third-party plugin distribution name.

    Returns:
        (LintResult) Refused when the name matches no reserved prefix.
    """
    if _PLUGIN_NAME.match(dist_name):
        return LintResult(ok=True, reason="")
    return LintResult(
        ok=False,
        reason=(
            f"plugin dist name {dist_name!r} matches none of {PLUGIN_PREFIXES} "
            "(FR-SYS-014): the plugin mechanism will not discover it"
        ),
    )
