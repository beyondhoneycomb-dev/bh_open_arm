"""The reaction-path precondition: `disable_torque()` must be absent (WP-2C-06).

The reaction the plan measures is `STOP_HOLD` — a *continuous* MIT position-hold send, not a
loop stop and not a torque cut (`02b` WP-2C-05: "정지 = 루프 중단이 아니다"). A QDD joint has
no brake, so a reaction that cuts torque with `bus.disable_torque()` drops the arm, and the
RID-9 watchdog dropping the command stream is the exact failure the audit hunts. This holds
at any latency and needs no clock, which is why it is the part of WP-2C-06 that stands
after the timing measurement was descoped: a reaction that cuts torque is a fall, whether
it takes 2 ms or 200 ms to get there.

This does not re-implement that scan. `backend.actuation.staticcheck.find_disable_torque`
already is it (WP-0A-01), and the single-source rule is why it is reused by import here
rather than copied: two scans for one safety absence is exactly the drift the audit hunts
for. The default root is the actuation spine, where the STOP_HOLD frame is emitted and which
`WP-2C-05` reuses as its reaction path; this module only *runs* the reused scan over it as a
publish-gating check and turns a non-empty result into a refusal.

An absence is only evidence when something was looked at, so the coverage of the run is
carried alongside its result. The reused scan reports what it found and never how much it
read, and its `rglob` walk over a root that does not exist yields exactly what a clean
reaction path yields, so a run that parsed no file is refused here rather than published as
a pass.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.actuation import StaticViolation, find_disable_torque

# Anchor for the default root and for the roots written into the artifact. The default is
# pinned to the tree this package lives in, not to the process working directory: a
# relative default resolves to a missing directory whenever the CLI is invoked from
# anywhere else, and a scan over a missing directory is silent, not clean.
_REPO_ROOT = Path(__file__).resolve().parents[2]

# The reaction path whose continuous STOP_HOLD MIT frame this bench measures: the actuation
# spine, where the scheduler tick and the CAN writer live and where `WP-2C-05` reuses the
# safety latch. This is the tree that must never cut torque on a reaction; a follower
# disconnect path elsewhere is not the reaction path and is out of scope here.
REACTION_PATH_TREE = Path("backend/actuation")

DEFAULT_REACTION_PATH_ROOT = _REPO_ROOT / REACTION_PATH_TREE


class DisableTorqueOnReactionPathError(Exception):
    """The static scan found `disable_torque` on the reaction path.

    Raised so the bench refuses to publish evidence for a reaction path that cuts torque
    instead of holding: a green here would certify a path that drops a brakeless arm
    (`02b` WP-2C-05).
    """


class ReactionPathScanEmptyError(Exception):
    """The `disable_torque` scan parsed no file, so it found nothing by not looking.

    Raised instead of publishing a pass: a missing root, a root that holds no Python file,
    and an exclusion list that covers everything all produce the same empty violation list
    as a clean reaction path, and only one of the four is evidence.
    """


def _repo_relative(root: Path) -> str:
    """Render a scan root for the artifact and for refusal messages.

    Args:
        root: The scanned root, absolute or relative.

    Returns:
        (str) Posix path relative to the repo root, or the absolute path when the root
        lies outside the repo.
    """
    resolved = root.resolve()
    try:
        return resolved.relative_to(_REPO_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def _scanned_file_count(root: Path, exclude: tuple[Path, ...]) -> int:
    """Count the files the reused scan parses under a root.

    Mirrors the reused scan's file enumeration — recursive `*.py`, hidden directories
    skipped, caller-excluded directories skipped — so the count is what was read rather
    than what happens to sit under the root. `test_no_disable_torque` pins the mirror by
    scanning a tree where every parsed file yields exactly one violation.

    Args:
        root: Directory handed to the scan.
        exclude: Directories the scan was told to skip.

    Returns:
        (int) Number of files the scan parses.
    """
    if not root.is_dir():
        return 0
    excluded = tuple(directory.resolve() for directory in exclude)
    count = 0
    for path in root.rglob("*.py"):
        if any(part.startswith(".") for part in path.relative_to(root).parts[:-1]):
            continue
        if any(directory in path.resolve().parents for directory in excluded):
            continue
        count += 1
    return count


@dataclass(frozen=True)
class NoDisableTorqueCheck:
    """The result of the `disable_torque` scan over the reaction path.

    Attributes:
        root: The reaction-path tree that was scanned.
        scanned_file_count: How many files the scan parsed. Zero means the run has no
            coverage and its empty violation list carries no information.
        violations: Any `disable_torque` references found; empty when the premise holds.
    """

    root: Path
    scanned_file_count: int
    violations: tuple[StaticViolation, ...]

    @property
    def scanned_anything(self) -> bool:
        """Whether the scan parsed at least one file.

        Returns:
            (bool) True when the run has coverage to speak from.
        """
        return self.scanned_file_count > 0

    @property
    def passed(self) -> bool:
        """Whether the reaction path was scanned and is free of `disable_torque`.

        Returns:
            (bool) True when the scan covered at least one file and found no reference.
        """
        return self.scanned_anything and not self.violations

    def as_record(self) -> dict[str, Any]:
        """Serialize the check for the evidence artifact.

        Returns:
            (dict[str, Any]) The scanned root, the file count behind the verdict, the pass
            flag, and any violation strings.
        """
        return {
            "root": _repo_relative(self.root),
            "symbol": "disable_torque",
            "passed": self.passed,
            "scanned_file_count": self.scanned_file_count,
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
        (NoDisableTorqueCheck) The scan result. `passed` requires both an absent symbol
        and a non-zero file count.
    """
    excluded = tuple(exclude)
    violations = tuple(find_disable_torque(root, exclude=excluded))
    return NoDisableTorqueCheck(
        root=root,
        scanned_file_count=_scanned_file_count(root, excluded),
        violations=violations,
    )


def assert_no_disable_torque(
    root: Path = DEFAULT_REACTION_PATH_ROOT,
    exclude: Iterable[Path] = (),
) -> NoDisableTorqueCheck:
    """Refuse to proceed unless the path was scanned and holds no `disable_torque`.

    Args:
        root: Reaction-path tree to scan; defaults to the actuation spine.
        exclude: Directories to skip explicitly.

    Returns:
        (NoDisableTorqueCheck) The passing check, for the caller to record as evidence.

    Raises:
        ReactionPathScanEmptyError: If the scan parsed no file.
        DisableTorqueOnReactionPathError: If any `disable_torque` reference was found.
    """
    check = check_no_disable_torque(root, exclude=exclude)
    if not check.scanned_anything:
        raise ReactionPathScanEmptyError(
            f"the disable_torque scan parsed no file under {_repo_relative(root)}: an empty "
            "result from an empty scan is not an absence, and this check gates a reaction "
            "path that must never cut torque (02b WP-2C-05)"
        )
    if check.violations:
        found = ", ".join(str(violation) for violation in check.violations)
        raise DisableTorqueOnReactionPathError(
            f"disable_torque on the reaction path under {_repo_relative(root)}: {found}; the "
            "reaction must be a continuous STOP_HOLD MIT frame, never a torque cut "
            "(02b WP-2C-05)"
        )
    return check
