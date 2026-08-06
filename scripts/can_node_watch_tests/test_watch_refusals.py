"""What must hold before a socket opens, and the one thing this tool deliberately does not ask.

Every other reader in this repo refuses until the operator says the arm is in their hands, because
`DamiaoMotorsBus.connect()` handshakes each motor with 0xFC and the arm is live from the socket.
This one sends only the disable frame, so that refusal would be theatre — and a refusal nobody
believes is how the ones that matter stop being read. What it does refuse is the case that would
make 0xFD dangerous: somebody else already holding the channel.
"""

from __future__ import annotations

import io
import os
import time
from collections.abc import Iterator
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from backend.can.lock import LockManager
from scripts import can_node_watch as watch
from scripts.can_node_watch_tests.watch_doubles import (
    INTERFACE_A,
    FakeNodeBus,
    channel_lister,
    lock_manager_factory,
    motors_for,
    two_channels,
    write_bench_records,
)

DOWN_STATE = "STOPPED"

# How far the scheduled instant may sit from `now + LEAD_SECONDS`. It only absorbs the time the
# command itself takes; the instant is what the operator reads off a wall clock, so it may not
# drift from the printed lead by anything they would notice.
SCHEDULING_SLACK_S = 5.0


@pytest.fixture
def free_locks(tmp_path: Path) -> Iterator[LockManager]:
    """A lock manager over a temporary lock directory, released at the end of the test."""
    manager = LockManager(lock_dir=str(tmp_path))
    yield manager
    manager.release_all()


@pytest.fixture
def bench(tmp_path: Path) -> Path:
    """A config directory holding this rig's binding and end-effector records."""
    write_bench_records(tmp_path, two_channels())
    return tmp_path


def _refuse_to_spawn(captures_root: Path, seconds: float, start_epoch: float) -> Path:
    """A spawn that fails the test: every refusal here comes before the fork."""
    raise AssertionError(
        f"a refusal was expected before this forked: {captures_root} {seconds} {start_epoch}"
    )


class SpawnRecorder:
    """Stands in for the fork, recording what the detached watch was handed.

    Attributes:
        handoffs: One `(seconds, start_epoch)` per spawn. Both are recorded because both are what
            the operator was promised on screen — a fork that got a different window than the
            timetable printed would be a timetable that lied.
    """

    def __init__(self) -> None:
        """Record nothing yet."""
        self.handoffs: list[tuple[float, float]] = []

    def __call__(self, captures_root: Path, seconds: float, start_epoch: float) -> Path:
        """Record the handoff and return the log path a real fork would have written to."""
        self.handoffs.append((seconds, start_epoch))
        return watch.session_dir(captures_root) / watch.LOG_FILENAME


def test_a_ready_bench_is_admitted_with_no_hand_on_the_arm(
    bench: Path, free_locks: LockManager
) -> None:
    """The whole point: this watch opens on a bench nobody is holding."""
    admission = watch.admit(two_channels(), free_locks, bench)

    assert admission.ok, admission.refusals
    assert len(admission.targets) == 2


def test_the_sibling_tools_hold_acknowledgement_is_not_an_option_here(bench: Path) -> None:
    """`canbind_session` cannot open without it; this tool refuses to have it at all.

    The flag exists there because the bus handshake energizes the arm. Carrying it here would
    claim this watch does the same thing, and an acknowledgement nobody needs is how the ones that
    matter stop being read.
    """
    from scripts.canbind_session import HOLD_ACKNOWLEDGEMENT_FLAG

    with pytest.raises(SystemExit), redirect_stdout(io.StringIO()):
        watch.main(["--captures", str(bench), HOLD_ACKNOWLEDGEMENT_FLAG])


def test_a_down_link_refuses_with_the_command_that_lifts_it(
    bench: Path, free_locks: LockManager
) -> None:
    """The tool never escalates; it prints what the operator runs in their own shell."""
    admission = watch.admit(two_channels(DOWN_STATE), free_locks, bench)

    assert not admission.ok
    assert any("sudo ip link set" in refusal for refusal in admission.refusals)


def test_a_held_channel_lock_refuses_the_watch(bench: Path) -> None:
    """Two readers on one channel is the exclusivity SocketCAN RAW cannot provide (01 FR-SYS-005).

    The refusal names the holder, and it names the consequence that is specific to this tool:
    if whoever holds the lock is an energized session, the disable frame drops that arm.
    """
    holder = LockManager(lock_dir=str(bench))
    assert holder.acquire_all([INTERFACE_A]).ok
    try:
        admission = watch.admit(two_channels(), LockManager(lock_dir=str(bench)), bench)
    finally:
        holder.release_all()

    assert not admission.ok
    joined = " ".join(admission.refusals)
    assert INTERFACE_A in joined
    assert str(os.getpid()) in joined
    assert "0xFD" in joined


def test_a_freed_channel_lock_admits_the_watch(bench: Path) -> None:
    """The lock refusal has to lift by itself, or the first held lock ends the procedure."""
    holder = LockManager(lock_dir=str(bench))
    assert holder.acquire_all([INTERFACE_A]).ok
    holder.release_all()

    admission = watch.admit(two_channels(), LockManager(lock_dir=str(bench)), bench)

    assert admission.ok, admission.refusals


def test_an_unreadable_bench_record_refuses_before_the_link_is_even_looked_at(
    tmp_path: Path, free_locks: LockManager
) -> None:
    """The record decides WHICH channels the rest is judged against.

    A link verdict over channels this watch would never open answers a question nobody asked.
    """
    admission = watch.admit(two_channels(DOWN_STATE), free_locks, tmp_path)

    assert len(admission.refusals) == 1
    assert admission.targets == ()


def test_the_default_command_opens_nothing_and_reports_the_preconditions(
    monkeypatch: pytest.MonkeyPatch, bench: Path, tmp_path: Path
) -> None:
    """With no `--run`, the entry point is a precondition report and nothing else."""
    monkeypatch.setattr(watch, "list_can_channels", channel_lister(two_channels()))
    monkeypatch.setattr(watch, "LockManager", lock_manager_factory(tmp_path))
    monkeypatch.setattr(watch, "default_config_directory", lambda: bench)
    monkeypatch.setattr(watch, "spawn_worker", _refuse_to_spawn)

    with redirect_stdout(io.StringIO()) as printed:
        code = watch.main(["--captures", str(tmp_path)])

    assert code == watch.EXIT_OK
    assert "0xFD" in printed.getvalue()
    assert not watch.state_path(tmp_path).exists()


def test_the_run_command_forks_nothing_when_a_precondition_fails(
    monkeypatch: pytest.MonkeyPatch, bench: Path, tmp_path: Path
) -> None:
    """The refusal is the entry point's, not a note in a docstring nobody runs."""
    monkeypatch.setattr(watch, "list_can_channels", channel_lister(two_channels(DOWN_STATE)))
    monkeypatch.setattr(watch, "LockManager", lock_manager_factory(tmp_path))
    monkeypatch.setattr(watch, "default_config_directory", lambda: bench)
    monkeypatch.setattr(watch, "spawn_worker", _refuse_to_spawn)

    with redirect_stdout(io.StringIO()) as printed:
        code = watch.main(["--captures", str(tmp_path), "--run"])

    assert code == watch.EXIT_REFUSED
    assert "sudo ip link set" in printed.getvalue()


def test_the_run_command_prints_a_wall_clock_timetable_and_returns_at_once(
    monkeypatch: pytest.MonkeyPatch, bench: Path, tmp_path: Path
) -> None:
    """A terminal shows nothing until the command ends, so the schedule has to precede the watch.

    What the operator gets back is absolute instants and their prompt; the measurement is somebody
    else's process by then.
    """
    spawned = SpawnRecorder()
    monkeypatch.setattr(watch, "list_can_channels", channel_lister(two_channels()))
    monkeypatch.setattr(watch, "LockManager", lock_manager_factory(tmp_path))
    monkeypatch.setattr(watch, "default_config_directory", lambda: bench)
    monkeypatch.setattr(watch, "spawn_worker", spawned)

    with redirect_stdout(io.StringIO()) as printed:
        code = watch.main(["--captures", str(tmp_path), "--run", "--seconds", "30"])

    assert code == watch.EXIT_OK
    assert len(spawned.handoffs) == 1
    seconds, start_epoch = spawned.handoffs[0]
    assert seconds == 30.0
    assert start_epoch == pytest.approx(time.time() + watch.LEAD_SECONDS, abs=SCHEDULING_SLACK_S)
    recorded = watch.read_watch(tmp_path)
    assert recorded is not None
    assert recorded[watch.FIELD_STATE] == watch.WATCH_SCHEDULED
    assert recorded[watch.FIELD_VERDICT_AT] in printed.getvalue()


def test_the_worker_opens_no_socket_when_the_lock_was_taken_in_the_meantime(
    monkeypatch: pytest.MonkeyPatch, bench: Path, tmp_path: Path
) -> None:
    """The operator's shell returned long ago; a lock taken since must stop the watch.

    Discovered after the socket is open, it is a second reader on a channel somebody else is
    already using — which is exactly what the lock exists to prevent.
    """
    holder = LockManager(lock_dir=str(tmp_path))
    assert holder.acquire_all([INTERFACE_A]).ok
    monkeypatch.setattr(watch, "list_can_channels", channel_lister(two_channels()))
    monkeypatch.setattr(watch, "LockManager", lock_manager_factory(tmp_path))
    monkeypatch.setattr(watch, "open_bus", _refuse_to_open)

    try:
        code = watch.run_worker(tmp_path, bench, seconds=1.0, start_epoch=0.0)
    finally:
        holder.release_all()

    assert code == watch.EXIT_REFUSED
    recorded = watch.read_watch(tmp_path)
    assert recorded is not None
    assert recorded[watch.FIELD_STATE] == watch.WATCH_REFUSED
    assert INTERFACE_A in recorded[watch.FIELD_REASON]


def _refuse_to_open(interface: str, locks: LockManager) -> FakeNodeBus:
    """An open that fails the test: the refusal it follows comes before any socket."""
    raise AssertionError(f"a socket was opened after a refusal: {interface} {locks}")


def test_a_bus_that_raises_mid_watch_becomes_the_recorded_verdict(
    monkeypatch: pytest.MonkeyPatch, bench: Path, tmp_path: Path
) -> None:
    """A traceback in a log nobody opens is a watch with no answer.

    `--status` is the only surface the operator reads once their shell has returned, so whatever
    stopped the watch has to arrive there.
    """
    monkeypatch.setattr(watch, "list_can_channels", channel_lister(two_channels()))
    monkeypatch.setattr(watch, "LockManager", lock_manager_factory(tmp_path))
    monkeypatch.setattr(watch, "open_bus", _raise_on_open)

    code = watch.run_worker(tmp_path, bench, seconds=1.0, start_epoch=0.0)

    assert code == watch.EXIT_REFUSED
    recorded = watch.read_watch(tmp_path)
    assert recorded is not None
    assert "socket" in recorded[watch.FIELD_REASON]


def _raise_on_open(interface: str, locks: LockManager) -> FakeNodeBus:
    """An open that fails the way a missing adapter does."""
    raise OSError(f"no socket for {interface} ({locks})")


def test_closing_shuts_every_channel_down() -> None:
    """A watch that left a socket open would refuse the next one through its own lock check."""
    buses = [FakeNodeBus(motors_for(())), FakeNodeBus(motors_for(()))]

    watch.close_buses(buses)

    assert all(bus.closed for bus in buses)
