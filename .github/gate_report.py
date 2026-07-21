"""Gate-state reporter and merge decision (WP-ENV-03 acceptance ⑤ and ⑦).

Two different artifacts (`02a` §2.2 WP-ENV-03 interface contract): CI *reports* a
gate state, and the pre-merge gate *enforces* it.

  ⑤ CI may auto-publish only `PASS` or `FAIL_BLOCKING`. `RETRY_WITH_VARIANT` and
    `DEGRADED_ACCEPTED` are issued by a human or a named variant policy — never by
    a job result. `map_job_result` collapses a boolean job outcome to exactly those
    two states, and `assert_auto_publishable` refuses to let CI emit the others.
  ⑦ A WP carrying a `FAIL_BLOCKING` gate does not merge. `merge_decision` blocks on
    any FAIL_BLOCKING among the gate states presented.

Inserts the repository root on `sys.path` so the gate-state vocabulary has a single
definition in `registry.checks.wp` rather than a second copy here.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from registry.checks.wp import (  # noqa: E402
    GATE_STATE_DEGRADED,
    GATE_STATE_FAIL_BLOCKING,
    GATE_STATE_PASS,
    GATE_STATE_RETRY,
)

# CI may publish these two automatically; nothing else.
AUTO_PUBLISHABLE = frozenset({GATE_STATE_PASS, GATE_STATE_FAIL_BLOCKING})
# These require a human or a named variant policy — CI auto-emitting them is banned.
HUMAN_ONLY_STATES = frozenset({GATE_STATE_RETRY, GATE_STATE_DEGRADED})


class AutoPublishError(ValueError):
    """Raised when CI attempts to auto-publish a human-only gate state."""


def map_job_result(passed: bool) -> str:
    """Collapse a boolean CI job outcome to an auto-publishable gate state.

    Args:
        passed: Whether the job succeeded.

    Returns:
        (str) `PASS` or `FAIL_BLOCKING` — never a retry/degraded state.
    """
    return GATE_STATE_PASS if passed else GATE_STATE_FAIL_BLOCKING


def assert_auto_publishable(state: str) -> str:
    """Refuse a state CI is not allowed to publish on its own.

    Args:
        state: The gate state a job is about to publish.

    Returns:
        (str) The same state when it is auto-publishable.

    Raises:
        AutoPublishError: When the state is human-only (retry/degraded) or unknown.
    """
    if state not in AUTO_PUBLISHABLE:
        raise AutoPublishError(
            f"CI may auto-publish only {sorted(AUTO_PUBLISHABLE)}; {state!r} needs a "
            "human or a named variant policy"
        )
    return state


@dataclass(frozen=True)
class MergeDecision:
    """Whether a set of gate states permits merge.

    Attributes:
        allowed: True when no gate blocks.
        blocking: The gate labels whose state is FAIL_BLOCKING.
    """

    allowed: bool
    blocking: tuple[str, ...]


def merge_decision(gate_states: dict[str, str]) -> MergeDecision:
    """Decide merge from a map of gate label to state (acceptance ⑦).

    Args:
        gate_states: Gate label to its published state.

    Returns:
        (MergeDecision) Blocked when any state is FAIL_BLOCKING.
    """
    blocking = tuple(
        sorted(label for label, state in gate_states.items() if state == GATE_STATE_FAIL_BLOCKING)
    )
    return MergeDecision(allowed=not blocking, blocking=blocking)
