"""The stop path cuts no torque, and torque does not come on until that is proven.

`04` NFR-MAN-002 makes a stop a Cat-2 hold frame rather than a torque cut, and `12`
NFR-SAF-009 is why: this arm has no holding brake, so `disable_torque` on the stop path is
a fall, not a stop. The scan itself is not reimplemented here —
`backend.actuation.staticcheck.find_disable_torque` already is it — but the actuation spine
is not the only tree that reaches the bus any more. This package now engages torque, so it
is a stop path too, and it gets the same scan over itself.

The scan runs as a precondition of engaging rather than as a report: a build whose stop path
can cut torque never reaches 0xFC. An absence is evidence only when something was read, and
the reused scan reports what it found and never how much it parsed, so the coverage is
enumerated here and a scan that read no file is refused rather than passed.

The torque drop this package does own — the operator's disengage — lives on the bus protocol
as `drop_torque` and is implemented by the bus, not here. The naming is load-bearing rather
than cosmetic. An operator ending a session and taking the arm's weight is not the stop path,
and keeping the banned symbol out of this tree is what lets the scan stay absolute instead of
carrying a per-file exemption list that the next edit widens.

`backend.stopbench` runs the same scan over the actuation spine. Neither package consumes the
other; both take the scan from `backend.actuation`, which is its single definition. There is
one scanner and two roots, not a wrapper chain.
"""

from __future__ import annotations

from pathlib import Path

from backend.actuation import StaticViolation, find_disable_torque

# This package's own directory. It is a stop path from the moment it can engage torque: the
# hold frames it parks on and the E-Stop facts it models both live here.
TORQUE_BRINGUP_ROOT = Path(__file__).resolve().parent


class TorqueCutOnStopPathError(Exception):
    """The static scan found a torque cut on the stop path.

    Raised instead of engaging. Cutting torque to stop a brakeless arm drops it, so a tree
    that can do so must not be given torque to drop in the first place (`04` NFR-MAN-002,
    `12` NFR-SAF-009).
    """


class StopPathScanEmptyError(Exception):
    """The scan parsed no file, so it found nothing by not looking.

    Raised instead of admitting the engage: a root holding no Python file yields the same
    empty violation list a clean stop path yields, and only one of the two is evidence.
    """


class StopPathRootMissingError(Exception):
    """The root the scan was aimed at is not a directory.

    Separate from the empty-scan refusal rather than folded into it, because the empty case is
    reached through the file list and a caller that returns something non-empty for a path that
    does not exist would satisfy it. A root that is not there is refused where it is read.
    """


def _resolved_root(root: Path | None) -> Path:
    """Resolve the root a scan runs over.

    The default is this package's directory, not the process working directory: the engage
    calls the refusal with no argument, so a default pointing anywhere else would scan a
    tree nobody engages from and report it clean.

    Args:
        root: Caller-supplied root, or None for this package.

    Returns:
        (Path) The directory the scan and its coverage enumeration both use.
    """
    return root if root is not None else TORQUE_BRINGUP_ROOT


def stop_path_files(root: Path | None = None) -> tuple[Path, ...]:
    """Enumerate the files the scan parses under a root.

    Mirrors the reused scan's traversal — recursive `*.py`, hidden directories skipped —
    because the scan returns findings and never its coverage. Callers use this to state
    which files an absence was established over.

    Args:
        root: Directory to enumerate; defaults to this package.

    Returns:
        (tuple[Path, ...]) The parsed files, resolved and ordered.
    """
    scanned = _resolved_root(root)
    if not scanned.is_dir():
        return ()
    return tuple(
        sorted(
            path.resolve()
            for path in scanned.rglob("*.py")
            if not any(part.startswith(".") for part in path.relative_to(scanned).parts[:-1])
        )
    )


def find_torque_cut_on_stop_path(root: Path | None = None) -> tuple[StaticViolation, ...]:
    """Scan a tree for a torque cut reachable from the stop path.

    Args:
        root: Directory to scan; defaults to this package.

    Returns:
        (tuple[StaticViolation, ...]) Offending references; empty when the premise holds.
    """
    return tuple(find_disable_torque(_resolved_root(root)))


def assert_stop_path_cuts_no_torque(root: Path | None = None) -> tuple[StaticViolation, ...]:
    """Refuse to proceed while a torque cut is reachable from the stop path.

    Args:
        root: Directory to scan; defaults to this package.

    Returns:
        (tuple[StaticViolation, ...]) The empty violation set, so a caller can record what
        was scanned rather than only that nothing was found.

    Raises:
        StopPathRootMissingError: If the root is not a directory.
        StopPathScanEmptyError: If the scan parsed no file.
        TorqueCutOnStopPathError: If any torque cut is reachable.
    """
    scanned = _resolved_root(root)
    if not scanned.is_dir():
        raise StopPathRootMissingError(
            f"the torque-cut scan was aimed at {scanned}, which is not a directory: a scan that "
            "opened nothing establishes nothing, and this precondition is what stands between a "
            "stop path that can cut torque and 0xFC (04 NFR-MAN-002, 12 NFR-SAF-009)"
        )
    if not stop_path_files(scanned):
        raise StopPathScanEmptyError(
            f"the torque-cut scan parsed no file under {scanned}: an empty result from an "
            "empty scan is not an absence, and this precondition is what stands between a "
            "stop path that can cut torque and 0xFC (04 NFR-MAN-002, 12 NFR-SAF-009)"
        )
    violations = find_torque_cut_on_stop_path(scanned)
    if violations:
        found = "; ".join(str(violation) for violation in violations)
        raise TorqueCutOnStopPathError(
            f"torque cut reachable from the stop path: {found}. A stop is a Cat-2 hold frame, "
            "not a torque cut — this arm has no holding brake, so cutting torque to stop it "
            "drops it (04 NFR-MAN-002, 12 NFR-SAF-009)"
        )
    return violations
