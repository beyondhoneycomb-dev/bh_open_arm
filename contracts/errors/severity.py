"""The 4-level diagnostic severity, borrowed in semantics only.

14 FR-OPS-017 fixes severity to four levels with the meaning of ROS 2
`diagnostic_msgs/DiagnosticStatus` — OK/WARN/ERROR plus STALE — but the runtime
carries no ROS 2, so this is a plain `IntEnum` and nothing here imports a message
type. The set is closed: a value outside it is rejected, never coerced.
"""

from __future__ import annotations

from enum import IntEnum


class Severity(IntEnum):
    """Diagnostic severity, OK < WARN < ERROR, with STALE as the staleness axis.

    The integer values are the contract (14 §2.10), so they are pinned here and
    must equal what `error_registry.yaml` declares under `severity_levels`.
    """

    OK = 0
    WARN = 1
    ERROR = 2
    STALE = 3


VALID_SEVERITY_VALUES: frozenset[int] = frozenset(int(level) for level in Severity)


def is_valid_severity(value: object) -> bool:
    """Report whether a value is one of the four fixed severity levels.

    A bool is rejected even though `bool` is an `int` subclass: `True`/`False`
    are never a severity, and accepting them would let `True == 1 == WARN` slip
    a type confusion through.

    Args:
        value: The candidate severity, from YAML it may be any type.

    Returns:
        (bool) True only for an int in {0, 1, 2, 3} that is not a bool.
    """
    if isinstance(value, bool):
        return False
    return isinstance(value, int) and value in VALID_SEVERITY_VALUES
