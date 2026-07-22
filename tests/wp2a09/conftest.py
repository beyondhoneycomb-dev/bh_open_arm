"""Fixtures for the WP-2A-09 preflight tests.

The one shared fixture holds a genuinely acquired writer lock over a temp directory, so
the pass case for item ④ runs against a real flock rather than a stubbed state. Pure
builders live in `builders.py`.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from backend.can.lock import LockManager, LockState
from tests.wp2a09.builders import TEST_IFACE


@pytest.fixture
def self_held_lock_state(tmp_path: Path) -> Iterator[LockState]:
    """Yield a writer-lock state this process holds, over a temp lock directory.

    Acquires the interface lock through the real `WP-0B-01` manager, yields its
    `lock_state`, and releases on teardown.
    """
    manager = LockManager(lock_dir=str(tmp_path))
    result = manager.acquire_all([TEST_IFACE])
    assert result.ok
    try:
        yield manager.lock_state([TEST_IFACE])[0]
    finally:
        manager.release_all()
