"""The reaction-path precondition: `disable_torque()` must be absent (WP-2C-06).

The reaction the plan measures is `STOP_HOLD` — a *continuous* MIT position-hold send, not a
loop stop and not a torque cut (`02b` WP-2C-05: "정지 = 루프 중단이 아니다"). A QDD joint has
no brake, so a reaction that cuts torque with `bus.disable_torque()` drops the arm, and the
RID-9 watchdog dropping the command stream is the exact failure the audit hunts. Measuring
the latency of such a path would just be timing the wrong thing, so this bench confirms by
static check that the reaction path holds no `disable_torque` *before* it measures.

This does not re-implement that scan. `backend.actuation.staticcheck.find_disable_torque`
already is it (WP-0A-01), and the single-source rule is why it is reused by import here
rather than copied: two scans for one safety absence is exactly the drift the audit hunts
for. The default root is the actuation spine, where the STOP_HOLD frame is emitted and which
`WP-2C-05` reuses as its reaction path; this module only *runs* the reused scan over it as a
publish-gating precondition and turns a non-empty result into a refusal.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.actuation import StaticViolation, find_disable_torque

# The reaction path whose continuous STOP_HOLD MIT frame this bench measures: the actuation
# spine, where the scheduler tick and the CAN writer live and where `WP-2C-05` reuses the
# safety latch. This is the tree that must never cut torque on a reaction; a follower
# disconnect path elsewhere is not the reaction path and is out of scope here.
DEFAULT_REACTION_PATH_ROOT = Path("backend/actuation")


class DisableTorqueOnReactionPathError(Exception):
    """The static scan found `disable_torque` on the reaction path.

    Raised so the bench refuses to measure a reaction path that cuts torque instead of
    holding: the latency of a wrong reaction path is not the quantity the gate wants, and a
    green here would certify a path that drops a brakeless arm (`02b` WP-2C-05).
    """


@dataclass(frozen=True)
class NoDisableTorqueCheck:
    """The result of the reaction-path `disable_torque` precondition.

    Attributes:
        root: The reaction-path tree that was scanned.
        violations: Any `disable_torque` references found; empty when the premise holds.
    """

    root: Path
    violations: tuple[StaticViolation, ...]

    @property
    def passed(self) -> bool:
        """Whether the reaction path is free of `disable_torque`.

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
    root: Path = DEFAULT_REACTION_PATH_ROOT,
    exclude: Iterable[Path] = (),
) -> NoDisableTorqueCheck:
    """Run the reused `disable_torque` scan over the reaction path.

    Args:
        root: Reaction-path tree to scan; defaults to the actuation spine.
        exclude: Directories to skip explicitly, forwarded to the reused scan.

    Returns:
        (NoDisableTorqueCheck) The scan result, `passed` when the symbol is absent.
    """
    violations = tuple(find_disable_torque(root, exclude=exclude))
    return NoDisableTorqueCheck(root=root, violations=violations)


def assert_no_disable_torque(
    root: Path = DEFAULT_REACTION_PATH_ROOT,
    exclude: Iterable[Path] = (),
) -> NoDisableTorqueCheck:
    """Refuse to proceed unless the reaction path is free of `disable_torque`.

    Args:
        root: Reaction-path tree to scan; defaults to the actuation spine.
        exclude: Directories to skip explicitly.

    Returns:
        (NoDisableTorqueCheck) The passing check, for the caller to record as evidence.

    Raises:
        DisableTorqueOnReactionPathError: If any `disable_torque` reference was found.
    """
    check = check_no_disable_torque(root, exclude=exclude)
    if not check.passed:
        found = ", ".join(str(violation) for violation in check.violations)
        raise DisableTorqueOnReactionPathError(
            f"disable_torque on the reaction path under {root.as_posix()}: {found}; the reaction "
            "must be a continuous STOP_HOLD MIT frame, never a torque cut (02b WP-2C-05)"
        )
    return check
