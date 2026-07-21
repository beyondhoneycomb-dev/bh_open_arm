"""Acceptance ① — a second bind must never yield `is_connected=True` (0 silent success).

`01` NFR-SYS-004: a CAN client may not report normal operation while another
process is bound to the interface. The gate enforces it as a precondition — the
double-bind check runs before any health report, and a detected binder returns
False whatever the transport says.

Two layers of "second bind" exist and split cleanly by what this host can do:

- Cooperating binder (a process holding our `WP-0B-01` flock): reproduced here
  with a *real second process* (`HeldLockProcess`), because `flock` is VFS-level
  and needs no CAN. The gate is exercised over 100 trials — 0 silent successes.
- Non-cooperating binder (a rogue `candump` / second python-can writer on a live
  SocketCAN interface): needs vcan or hardware, absent on this host, so the live
  100-trial version is skipped with a reason and re-verified by
  `reverify.reverify_gate_from_capture` against a real `WP-0B-03` capture.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.can.bind.connection_gate import ConnectionGate
from backend.can.bind.double_bind import (
    DoubleBindCheck,
    DoubleBindError,
    ForeignBinder,
    LockBindProbe,
    StaticBindProbe,
)
from backend.can.lock.harness import HeldLockProcess
from backend.can.lock.manager import LockManager

_TRIALS = 100


def _transport_up() -> bool:
    """A transport probe that always reports connected, isolating the gate's decision."""
    return True


def _transport_down() -> bool:
    """A transport probe that always reports disconnected."""
    return False


def _injected_binder(iface: str) -> ForeignBinder:
    """A foreign binder record for `iface`, as a live probe would report it."""
    return ForeignBinder(
        iface=iface, source="replay", detail="second writer on bus", holder_pid=4242
    )


def test_injected_binder_never_reports_connected() -> None:
    """With a binder injected, is_connected is False across every trial (0 silent success)."""
    gate = ConnectionGate(DoubleBindCheck([StaticBindProbe([_injected_binder("can0")])]))
    results = [gate.is_connected(["can0"], _transport_up) for _ in range(_TRIALS)]
    assert results.count(True) == 0, "a second bind must never yield is_connected=True"


def test_clean_interface_reports_transport_answer(tmp_path: Path) -> None:
    """With no binder, the report is exactly the transport's own answer."""
    manager = LockManager(lock_dir=str(tmp_path))
    assert manager.acquire_all(["can0"]).ok  # held_by_self -> not a foreign binder
    gate = ConnectionGate(DoubleBindCheck([LockBindProbe(manager)]))
    try:
        assert gate.is_connected(["can0"], _transport_up) is True
        assert gate.is_connected(["can0"], _transport_down) is False
    finally:
        manager.release_all()


def test_real_second_process_bind_never_reports_connected(tmp_path: Path) -> None:
    """A real second process holding the flock blocks a connected report (acceptance ①).

    This is the cooperating-binder layer, run for real here: a separate process
    holds the lock, our manager does not, and the gate refuses across 100 trials
    while naming the foreign holder's PID.
    """
    manager = LockManager(lock_dir=str(tmp_path))
    gate = ConnectionGate(DoubleBindCheck([LockBindProbe(manager)]))
    with HeldLockProcess(str(tmp_path), ["can0"]) as holder:
        binders = gate.foreign_binders(["can0"])
        assert [binder.holder_pid for binder in binders] == [holder.pid]
        results = [gate.is_connected(["can0"], _transport_up) for _ in range(_TRIALS)]
        assert results.count(True) == 0, "a foreign flock holder must never yield is_connected=True"


def test_assert_absent_raises_naming_the_binder() -> None:
    """The loud precondition raises and names the evidence."""
    check = DoubleBindCheck([StaticBindProbe([_injected_binder("can0")])])
    with pytest.raises(DoubleBindError, match="second bind present"):
        check.assert_absent(["can0"])


def test_binder_on_other_iface_does_not_gate_this_one() -> None:
    """A binder on can1 does not refuse a report about can0 (probe scoping)."""
    gate = ConnectionGate(DoubleBindCheck([StaticBindProbe([_injected_binder("can1")])]))
    assert gate.is_connected(["can0"], _transport_up) is True
    assert gate.is_connected(["can1"], _transport_up) is False


@pytest.mark.skip(
    reason="needs vcan/real CAN: a non-cooperating second SocketCAN bind (candump / "
    "2nd python-can writer) cannot be created on this no-vcan host. The gate mechanism "
    "is verified here via the real-flock and injected-binder tests; the live 100-trial "
    "SocketCAN version is re-verified by reverify.reverify_gate_from_capture against a "
    "real WP-0B-03 capture."
)
def test_live_socketcan_second_bind_100_trials() -> None:  # pragma: no cover - deferred
    """Deferred: live second SocketCAN bind, 0/100 silent successes (acceptance ①, live)."""
    raise AssertionError("must run against vcan/hardware, not synthetic state")
