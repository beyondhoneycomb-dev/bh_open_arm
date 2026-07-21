"""Violation fixture: a second, divergent lock-path literal outside paths.py.

Proves `staticcheck.find_divergent_lock_paths` bites — a hardcoded copy of the lock
path is exactly the `01`/`02` disagreement surviving as two definitions, which
acceptance ⑤ forbids.
"""

from __future__ import annotations

from pathlib import Path


def bad_path(iface: str) -> Path:
    """Build a lock path from a hardcoded literal instead of the path authority."""
    return Path("/var/lock") / f"openarm-{iface}.lock"
