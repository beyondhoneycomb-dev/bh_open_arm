"""Acceptance ⑨ — concurrent activation of one package resolves to a single winner.

Contention is created with real processes rather than threads, because the guarantee being
tested is a cross-process one: two workflows are two processes, and a lock that only holds
within an interpreter would pass a threaded test while failing in production.

Children block on a pipe until the parent releases them all at once, so they collide inside the
transition rather than running in sequence.
"""

from __future__ import annotations

import contextlib
import os
import time
from collections.abc import Iterator
from pathlib import Path

import registry.state.store as store_module
from registry.state.model import IllegalTransitionError, WorkPackageState
from registry.state.store import StateStore

CONTENDERS = 8
ROUNDS = 25
EVIDENCE = "sha256:" + "c" * 64
WP = "WP-BOOT-04"
WIN_EXIT = 0
LOSE_EXIT = 1
ERROR_EXIT = 2
WIDEN_RACE_SECONDS = 0.02

# Captured before any sabotage so the widened-window double can still reach the real writer.
_REAL_ATOMIC_WRITE = store_module._atomic_write_json


def _race_activation(root: Path, contenders: int, sabotage_lock: bool) -> int:
    """Have several processes race to activate the same package.

    Args:
        root: Store directory.
        contenders: How many processes to fork.
        sabotage_lock: When true, children run with the store lock disabled and a widened
            read-to-write window. Used only by the negative control.

    Returns:
        (int): Number of processes that believe they won.

    Raises:
        AssertionError: A child failed for a reason other than losing the race. Treating an
            unexpected error as a loss would let a broken harness report a clean single winner.
    """
    read_fd, write_fd = os.pipe()
    pids: list[int] = []

    for _ in range(contenders):
        pid = os.fork()
        if pid == 0:
            os.close(write_fd)
            os.read(read_fd, 1)
            if sabotage_lock:
                store_module.StateStore._exclusive = _no_lock
                store_module._atomic_write_json = _slow_write
            try:
                StateStore(root).transition(WP, WorkPackageState.ACTIVE, "race", EVIDENCE)
            except IllegalTransitionError:
                os._exit(LOSE_EXIT)
            except BaseException:
                os._exit(ERROR_EXIT)
            os._exit(WIN_EXIT)
        pids.append(pid)

    os.close(read_fd)
    os.write(write_fd, b"\x00" * contenders)
    os.close(write_fd)

    winners = 0
    for pid in pids:
        _, status = os.waitpid(pid, 0)
        code = os.waitstatus_to_exitcode(status)
        assert code != ERROR_EXIT, "a contender crashed instead of winning or losing"
        if code == WIN_EXIT:
            winners += 1
    return winners


@contextlib.contextmanager
def _no_lock(self: StateStore) -> Iterator[None]:
    """Stand in for the store lock while taking no lock at all.

    Args:
        self: The store instance; unused.

    Yields:
        (None): Control, with nothing held.
    """
    yield


def _slow_write(path: Path, payload: dict[str, object]) -> None:
    """Delay the commit to widen the window between reading state and writing it.

    Args:
        path: Destination document.
        payload: Document to persist.
    """
    time.sleep(WIDEN_RACE_SECONDS)
    _REAL_ATOMIC_WRITE(path, payload)


def test_single_winner_under_contention(tmp_path: Path) -> None:
    """Acceptance ⑨ — exactly one activation succeeds, and the log records exactly one."""
    for round_index in range(ROUNDS):
        root = tmp_path / f"round{round_index}"
        winners = _race_activation(root, CONTENDERS, sabotage_lock=False)
        assert winners == 1, f"round {round_index}: {winners} winners"

        store = StateStore(root)
        activations = [
            record
            for record in store.transitions()
            if record.wp == WP and record.new_state is WorkPackageState.ACTIVE
        ]
        assert len(activations) == 1, "double activation recorded in the log"
        assert activations[0].previous_state is WorkPackageState.NOT_STARTED
        assert store.state_of(WP) is WorkPackageState.ACTIVE


def test_violation_fixture_unlocked_store_double_activates(tmp_path: Path) -> None:
    """Negative control: with the lock removed, the same race produces multiple winners.

    Without this, a single-winner result would be indistinguishable from a race that never
    actually happened.
    """
    observed_double = False
    for round_index in range(ROUNDS):
        root = tmp_path / f"broken{round_index}"
        if _race_activation(root, CONTENDERS, sabotage_lock=True) > 1:
            observed_double = True
            break

    assert observed_double, "the race never collided; the single-winner result proves nothing"
