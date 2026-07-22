"""The stop-path precondition: `disable_torque()` must be absent (WP-2A-06 acceptance ③).

`03` §5.7 fixes the stop-path architecture: an immediate stop is one MIT position-hold
frame, and `04` NFR-MAN-002 is explicit that cutting torque with `bus.disable_torque()`
on the stop path cannot meet the budget and drops a brakeless arm. WP-2A-06 acceptance ③
requires this absence be confirmed by static check *before* the latency is measured — a
measurement of a wrong stop path would just be measuring the wrong thing.

This does not re-implement that scan. `backend.actuation.staticcheck.find_disable_torque`
already is it (WP-0A-01, acceptance ⑦), and the single-source rule is why it is reused by
import here rather than copied: two scans for one absence is exactly the drift the audit
hunts for. This module only *runs* the reused scan over the stop path as a publish-gating
precondition and turns a non-empty result into a refusal.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.actuation import StaticViolation, find_disable_torque

# The stop path whose Cat-2 hold frame this bench measures: the actuation spine, where the
# lease expiry, the decider, the scheduler tick and the CAN writer live. This is the tree
# `04` NFR-MAN-002 forbids `disable_torque()` in; the follower's disconnect path elsewhere
# is not the stop path and is out of scope for this precondition.
DEFAULT_STOP_PATH_ROOT = Path("backend/actuation")


class DisableTorqueOnStopPathError(Exception):
    """The static scan found `disable_torque` on the stop path.

    Raised so the bench refuses to measure a stop path that cuts torque instead of
    holding: the latency of a wrong stop path is not the quantity the gate wants, and a
    green here would certify a path that drops a brakeless arm (`04` NFR-MAN-002).
    """


@dataclass(frozen=True)
class NoDisableTorqueCheck:
    """The result of the acceptance-③ precondition over the stop path.

    Attributes:
        root: The stop-path tree that was scanned.
        violations: Any `disable_torque` references found; empty when the premise holds.
    """

    root: Path
    violations: tuple[StaticViolation, ...]

    @property
    def passed(self) -> bool:
        """Whether the stop path is free of `disable_torque`.

        Returns:
            (bool) True when no reference was found.
        """
        return not self.violations

    def as_record(self) -> dict[str, Any]:
        """Serialize the check for the evidence artifact.

        Returns:
            (dict[str, Any]) The scanned root, the pass flag, and any violation strings.
        """
        return {
            "root": self.root.as_posix(),
            "symbol": "disable_torque",
            "passed": self.passed,
            "reused_scan": "backend.actuation.staticcheck.find_disable_torque",
            "violations": [str(violation) for violation in self.violations],
        }


def check_no_disable_torque(
    root: Path = DEFAULT_STOP_PATH_ROOT,
    exclude: Iterable[Path] = (),
) -> NoDisableTorqueCheck:
    """Run the reused `disable_torque` scan over the stop path (acceptance ③).

    Args:
        root: Stop-path tree to scan; defaults to the actuation spine.
        exclude: Directories to skip explicitly, forwarded to the reused scan.

    Returns:
        (NoDisableTorqueCheck) The scan result, `passed` when the symbol is absent.
    """
    violations = tuple(find_disable_torque(root, exclude=exclude))
    return NoDisableTorqueCheck(root=root, violations=violations)


def assert_no_disable_torque(
    root: Path = DEFAULT_STOP_PATH_ROOT,
    exclude: Iterable[Path] = (),
) -> NoDisableTorqueCheck:
    """Refuse to proceed unless the stop path is free of `disable_torque`.

    Args:
        root: Stop-path tree to scan; defaults to the actuation spine.
        exclude: Directories to skip explicitly.

    Returns:
        (NoDisableTorqueCheck) The passing check, for the caller to record as evidence.

    Raises:
        DisableTorqueOnStopPathError: If any `disable_torque` reference was found.
    """
    check = check_no_disable_torque(root, exclude=exclude)
    if not check.passed:
        found = ", ".join(str(violation) for violation in check.violations)
        raise DisableTorqueOnStopPathError(
            f"disable_torque on the stop path under {root.as_posix()}: {found}; the stop path "
            "must be a Cat-2 hold frame, never a torque cut (04 NFR-MAN-002, acceptance ③)"
        )
    return check
