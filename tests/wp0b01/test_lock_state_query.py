"""`01` FR-SYS-009 — runtime lock-state query, the data behind the REST + WS display.

The manager exposes a snapshot the transport layer serialises: for each channel,
whether we hold it and, when another process does, who. The holder report projects to
a JSON-ready mapping so the WS/REST layer never reaches into dataclass internals.
"""

from __future__ import annotations

from pathlib import Path

from backend.can.lock.harness import HeldLockProcess
from backend.can.lock.manager import LockManager


def test_state_reports_self_held_channels(tmp_path: Path) -> None:
    """Channels this manager holds report `held_by_self` with no foreign holder."""
    manager = LockManager(lock_dir=str(tmp_path))
    assert manager.acquire_all(["can0", "can1"]).ok
    states = {state.iface: state for state in manager.lock_state(["can0", "can1"])}

    assert states["can0"].held_by_self
    assert states["can0"].holder is None
    assert states["can0"].lock_path.endswith("openarm-can0.lock")
    manager.release_all()


def test_state_reports_a_foreign_holder(tmp_path: Path) -> None:
    """A channel held by another process reports that holder's PID and command line."""
    lock_dir = str(tmp_path)
    manager = LockManager(lock_dir=lock_dir)
    with HeldLockProcess(lock_dir, ["can2"]) as holder:
        (state,) = manager.lock_state(["can2"])
        assert not state.held_by_self
        assert state.holder is not None
        assert state.holder.holder_pid == holder.pid

        projected = state.holder.as_dict()
        assert projected["holder_pid"] == holder.pid
        assert set(projected) == {
            "iface",
            "holder_pid",
            "holder_cmdline",
            "lock_path",
            "acquired_at",
        }


def test_state_reports_a_free_channel(tmp_path: Path) -> None:
    """An unheld, uncontended channel reports neither self-held nor a holder."""
    manager = LockManager(lock_dir=str(tmp_path))
    (state,) = manager.lock_state(["can0"])
    assert not state.held_by_self
    assert state.holder is None
