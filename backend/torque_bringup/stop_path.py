"""The stop path cuts no torque, and torque does not come on until that is proven.

`04` NFR-MAN-002 makes a stop a Cat-2 hold frame rather than a torque cut, and `12`
NFR-SAF-009 is why: this arm has no holding brake, so `disable_torque` on the stop path is
a fall, not a stop. The scan itself is not reimplemented here —
`backend.actuation.staticcheck.find_disable_torque` already is it — but the actuation spine
is not the only tree that reaches the bus any more. This package now engages torque, so it
is a stop path too, and it gets the same scan over itself.

The scan runs as a precondition of engaging rather than as a report: a build whose stop path
can cut torque never reaches 0xFC.

The torque drop this package does own — the operator's disengage — lives on the bus protocol
as `drop_torque` and is implemented by the bus, not here. The naming is load-bearing rather
than cosmetic. An operator ending a session and taking the arm's weight is not the stop path,
and keeping the banned symbol out of this tree is what lets the scan stay absolute instead of
carrying a per-file exemption list that the next edit widens.

`backend.stopbench` wraps the same scan for the actuation spine. This does not import that
wrapper: `backend.stopbench` imports this package, and consuming it back would close the
cycle. Both consume `backend.actuation` directly, which is the single definition.
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


def find_torque_cut_on_stop_path(root: Path | None = None) -> tuple[StaticViolation, ...]:
    """Scan a tree for a torque cut reachable from the stop path.

    Args:
        root: Directory to scan; defaults to this package.

    Returns:
        (tuple[StaticViolation, ...]) Offending references; empty when the premise holds.
    """
    scanned = root if root is not None else TORQUE_BRINGUP_ROOT
    return tuple(find_disable_torque(scanned))


def assert_stop_path_cuts_no_torque(root: Path | None = None) -> tuple[StaticViolation, ...]:
    """Refuse to proceed while a torque cut is reachable from the stop path.

    Args:
        root: Directory to scan; defaults to this package.

    Returns:
        (tuple[StaticViolation, ...]) The empty violation set, so a caller can record what
        was scanned rather than only that nothing was found.

    Raises:
        TorqueCutOnStopPathError: If any torque cut is reachable.
    """
    violations = find_torque_cut_on_stop_path(root)
    if violations:
        found = "; ".join(str(violation) for violation in violations)
        raise TorqueCutOnStopPathError(
            f"torque cut reachable from the stop path: {found}. A stop is a Cat-2 hold frame, "
            "not a torque cut — this arm has no holding brake, so cutting torque to stop it "
            "drops it (04 NFR-MAN-002, 12 NFR-SAF-009)"
        )
    return violations
