"""Real-fixture re-verification hook for the lock manager (acceptance ⑥, plan 02a §4.1).

Almost every lock acceptance runs here, because `flock` is VFS-level and needs no
CAN hardware. What does not run here is the end-to-end claim that our cooperative
lock is honoured *in front of the real robot connect path* — that a real second
`openarm-can` / python-can writer is actually kept out while we hold the flock, and
that the holder record we parse matches one a real rig wrote. That needs vcan or the
robot, neither of which exists on this host, so it is deferred — but not asserted
green and not dropped.

This is the re-verification hook the deferral is required to ship: the moment a
fixture directory of real captured lock files is supplied, `reverify_from_fixture`
re-runs the holder-report parse against them and checks each against the recorded
expectation. Until then the bound test skips with a reason. The fixture directory
holds captured `openarm-<iface>.lock` files plus an `expected.json` of
`{iface: {holder_pid, holder_cmdline?}}`.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from backend.can.lock.holder import LockHolderReport, read_holder_record
from backend.can.lock.paths import normalize_lock_path

# Environment variable a caller sets to point the hook at a real capture directory.
FIXTURE_ENV_VAR = "OPENARM_LOCK_REAL_FIXTURE"
EXPECTED_FILENAME = "expected.json"


@dataclass(frozen=True)
class ReverifyResult:
    """Outcome of re-verifying one captured lock file against its expectation.

    Attributes:
        iface: Interface the captured lock guards.
        report: Holder report parsed from the real capture.
        matched: True when the parsed report matched the recorded expectation.
        detail: Human-readable mismatch detail, empty on a match.
    """

    iface: str
    report: LockHolderReport
    matched: bool
    detail: str


def fixture_dir_from_env() -> Path | None:
    """Return the real-fixture directory named by the environment, if set and present.

    Returns:
        (Path | None) The directory, or None when unset or absent.
    """
    raw = os.environ.get(FIXTURE_ENV_VAR)
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_dir() else None


def reverify_from_fixture(fixture_dir: Path) -> list[ReverifyResult]:
    """Re-run the holder-report parse against real captured lock files.

    Parses each captured `openarm-<iface>.lock` with the same reader the live refusal
    path uses, and checks the holder PID (and command line, when the expectation
    records one) against `expected.json`. This is the identical check the synthetic
    tests run, pointed at real bytes.

    Args:
        fixture_dir: Directory of captured lock files plus `expected.json`.

    Returns:
        (list[ReverifyResult]) One result per captured interface, sorted by iface.

    Raises:
        FileNotFoundError: If `expected.json` is missing from the directory.
    """
    expected_path = fixture_dir / EXPECTED_FILENAME
    if not expected_path.is_file():
        raise FileNotFoundError(f"missing {EXPECTED_FILENAME} in {fixture_dir}")
    expected = json.loads(expected_path.read_text(encoding="utf-8"))

    results: list[ReverifyResult] = []
    for iface, want in sorted(expected.items()):
        lock_path = normalize_lock_path(iface, str(fixture_dir))
        fd = os.open(lock_path, os.O_RDONLY)
        try:
            report = read_holder_record(fd, iface, lock_path)
        finally:
            os.close(fd)
        results.append(_compare(iface, report, want))
    return results


def _compare(iface: str, report: LockHolderReport, want: dict[str, object]) -> ReverifyResult:
    """Compare a parsed report against a recorded expectation.

    Args:
        iface: Interface under check.
        report: Report parsed from the real capture.
        want: Expected fields, at least `holder_pid`.

    Returns:
        (ReverifyResult) The comparison outcome.
    """
    mismatches: list[str] = []
    if report.holder_pid != want.get("holder_pid"):
        mismatches.append(f"pid {report.holder_pid} != {want.get('holder_pid')}")
    if "holder_cmdline" in want and report.holder_cmdline != want["holder_cmdline"]:
        mismatches.append(f"cmdline {report.holder_cmdline!r} != {want['holder_cmdline']!r}")
    return ReverifyResult(
        iface=iface,
        report=report,
        matched=not mismatches,
        detail="; ".join(mismatches),
    )
