"""F24 session-start check — `use_velocity_and_torque` must be set on both arms (`14` F24).

`14` F24: if `use_velocity_and_torque` is left unset, the driver silently drops the torque
channel — no error, just missing data discovered later in the recording. The defence is to
check it at session start, before any data is collected, on both the follower and the leader,
and refuse to start when either arm would lose torque.

"Unset" and "explicitly False" are the same failure here: a missing key is exactly the
default-off case F24 warns about, so both are treated as "would lose torque".
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

CONFIG_KEY = "use_velocity_and_torque"


class TorqueDataLossError(RuntimeError):
    """A session would start with torque data silently dropped on at least one arm (F24)."""


@dataclass(frozen=True)
class TorqueCheckResult:
    """The outcome of the F24 session-start check.

    Attributes:
        follower_ok: Whether the follower has `use_velocity_and_torque` set truthy.
        leader_ok: Whether the leader has it set truthy.
        problems: Human-readable descriptions of each arm that would lose torque.
    """

    follower_ok: bool
    leader_ok: bool
    problems: tuple[str, ...]

    @property
    def ok(self) -> bool:
        """Whether both arms are configured to keep torque data.

        Returns:
            (bool) True iff neither arm would lose torque.
        """
        return self.follower_ok and self.leader_ok


def _is_set_truthy(config: Mapping[str, Any]) -> bool:
    """Report whether a config sets `use_velocity_and_torque` to a truthy value.

    Args:
        config: An arm configuration mapping.

    Returns:
        (bool) True only when the key is present and truthy.
    """
    return bool(config.get(CONFIG_KEY, False))


def check_velocity_and_torque(
    follower: Mapping[str, Any],
    leader: Mapping[str, Any],
) -> TorqueCheckResult:
    """Check both arms for the F24 torque-loss condition.

    Args:
        follower: Follower arm configuration.
        leader: Leader arm configuration.

    Returns:
        (TorqueCheckResult) Per-arm verdicts and problem descriptions.
    """
    follower_ok = _is_set_truthy(follower)
    leader_ok = _is_set_truthy(leader)
    problems: list[str] = []
    if not follower_ok:
        problems.append(f"follower {CONFIG_KEY} unset/false — torque data would be silently lost")
    if not leader_ok:
        problems.append(f"leader {CONFIG_KEY} unset/false — torque data would be silently lost")
    return TorqueCheckResult(
        follower_ok=follower_ok,
        leader_ok=leader_ok,
        problems=tuple(problems),
    )


def assert_velocity_and_torque_at_session_start(
    follower: Mapping[str, Any],
    leader: Mapping[str, Any],
) -> None:
    """Raise at session start if either arm would silently lose torque.

    Args:
        follower: Follower arm configuration.
        leader: Leader arm configuration.

    Raises:
        TorqueDataLossError: If `use_velocity_and_torque` is unset/false on either arm.
    """
    result = check_velocity_and_torque(follower, leader)
    if not result.ok:
        raise TorqueDataLossError("; ".join(result.problems))
