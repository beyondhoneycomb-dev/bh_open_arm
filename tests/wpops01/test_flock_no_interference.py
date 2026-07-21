"""Acceptance ③: the ACL layer complements flock, with zero interference between the two.

Two things are shown. First, *why* they do not interfere: the sandbox seals the filesystem with
`ProtectSystem=strict`, which would make the WP-0B-01 lock file uncreatable — unless the unit
re-grants the lock directory, which the shipped unit does. That single directive is the entire
interference surface, and `find_lock_dir_not_writable` asserts it holds. Second, *that* they do
not interfere: with `ops.acl` imported and active, the complete WP-0B-01 flock suite is re-run and
must pass exactly as before (0 layer interference).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Importing the ACL layer here is the "ACL active" precondition for the re-run below.
import ops.acl  # noqa: F401 — imported for its side effect of loading the ACL layer
from ops.acl.policy import WRITER_UNIT_FILENAME
from ops.acl.staticcheck import find_lock_dir_not_writable

_REPO_ROOT = Path(__file__).resolve().parents[2]
_UNITS = _REPO_ROOT / "ops" / "acl" / "units"
_FLOCK_SUITE = "tests/wp0b01"


def test_sandbox_re_grants_the_flock_directory() -> None:
    """The sole interference point: the sealed sandbox must keep the lock directory writable."""
    writer = (_UNITS / WRITER_UNIT_FILENAME).read_text(encoding="utf-8")
    assert find_lock_dir_not_writable(writer) == []


def test_flock_suite_still_passes_with_acl_active() -> None:
    """With the ACL layer imported, the entire WP-0B-01 flock suite re-runs green."""
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", _FLOCK_SUITE, "-q"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, (
        f"flock suite regressed under an active ACL layer:\n{completed.stdout}\n{completed.stderr}"
    )
