"""Acceptance ④ — connect ordering: no socket opens before every channel lock is held.

Two halves, both required. Runtime: `guarded_connect` refuses to invoke the socket-
opening callable unless the manager already holds every channel, so an out-of-order
open never runs. Static: `find_can_open_without_lock_import` flags any module that
opens an `AF_CAN` socket with no lock layer in scope, so the absence is checked over
every line, not just the paths a test happened to exercise.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.can.lock import LockManager, LockOrderingError, assert_lock_held, guarded_connect
from backend.can.lock.staticcheck import find_can_open_without_lock_import

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LOCK_PACKAGE = _REPO_ROOT / "backend" / "can" / "lock"
_FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_guarded_connect_runs_open_only_when_all_held(tmp_path: Path) -> None:
    """With every channel held, the socket-opening callable is invoked."""
    manager = LockManager(lock_dir=str(tmp_path))
    assert manager.acquire_all(["can0", "can1"]).ok
    opened: list[str] = []

    def _open() -> str:
        opened.append("socket")
        return "connection"

    assert guarded_connect(manager, ["can0", "can1"], _open) == "connection"
    assert opened == ["socket"]
    manager.release_all()


def test_guarded_connect_rejects_and_never_opens_when_a_lock_is_missing(tmp_path: Path) -> None:
    """A missing channel lock rejects at runtime and never calls the opener."""
    manager = LockManager(lock_dir=str(tmp_path))
    assert manager.acquire_all(["can0"]).ok  # can1 deliberately not held
    opened: list[str] = []

    def _open() -> str:
        opened.append("socket")
        return "connection"

    with pytest.raises(LockOrderingError):
        guarded_connect(manager, ["can0", "can1"], _open)
    assert opened == [], "the socket opener must not run when a lock is missing"
    manager.release_all()


def test_assert_lock_held_is_the_measurement_precondition(tmp_path: Path) -> None:
    """The bare precondition raises when unheld — the form the measurement WPs use."""
    manager = LockManager(lock_dir=str(tmp_path))
    with pytest.raises(LockOrderingError):
        assert_lock_held(manager, ["can0"])
    assert manager.acquire_all(["can0"]).ok
    assert_lock_held(manager, ["can0"])  # now a no-op, does not raise
    manager.release_all()


def test_lock_package_opens_no_can_socket() -> None:
    """The lock layer itself never opens a CAN socket — it is a pure precondition."""
    assert find_can_open_without_lock_import(_LOCK_PACKAGE) == []


def test_static_scan_flags_an_unguarded_open() -> None:
    """The static half bites: a CAN open with no lock import is flagged."""
    assert find_can_open_without_lock_import(_FIXTURES / "unguarded_can_open.py")


def test_static_scan_allows_a_guarded_open() -> None:
    """The static half does not over-fire: a lock-imported open is not flagged."""
    assert find_can_open_without_lock_import(_FIXTURES / "guarded_can_open.py") == []
