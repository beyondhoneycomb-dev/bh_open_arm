"""Acceptance ⑥ — 100 crashes injected mid-transition, zero store corruption.

The crash is a real one. A forked child is killed with `os._exit`, which runs no cleanup, no
`atexit`, and flushes nothing — the same thing a power loss does to a half-finished write. Three
injection points bracket the atomic rename: before the data is flushed, after the flush but
before the rename, and after the rename but before the directory entry is synced.

An exception-based "crash" would prove much less, because unwinding gives the code a chance to
tidy up that a real crash never grants.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from registry.state.model import WorkPackageState
from registry.state.store import StateStore

CRASH_ITERATIONS = 100
EVIDENCE = "sha256:" + "b" * 64
WP = "WP-BOOT-04"

BEFORE_FLUSH = "before_flush"
BEFORE_RENAME = "before_rename"
AFTER_RENAME = "after_rename"
CRASH_POINTS = (BEFORE_FLUSH, BEFORE_RENAME, AFTER_RENAME)
CRASH_EXIT_CODE = 9


class _Killer:
    """Replaces an `os` primitive so that the Nth call terminates the process."""

    def __init__(self, kill_on_call: int) -> None:
        self.kill_on_call = kill_on_call
        self.calls = 0

    def __call__(self, *args: object, **kwargs: object) -> None:
        self.calls += 1
        if self.calls >= self.kill_on_call:
            os._exit(CRASH_EXIT_CODE)


def _crash_in_child(root: Path, crash_point: str, new_state: WorkPackageState) -> int:
    """Attempt a transition in a forked child that dies at the given point.

    Args:
        root: Store directory.
        crash_point: Which primitive to sabotage.
        new_state: State the child tries to commit.

    Returns:
        (int): The child's exit status as reported by `os.waitpid`.
    """
    pid = os.fork()
    if pid == 0:
        if crash_point == BEFORE_FLUSH:
            os.fsync = _Killer(kill_on_call=1)
        elif crash_point == BEFORE_RENAME:
            os.replace = _Killer(kill_on_call=1)
        else:
            # First fsync is the data file, second is the parent directory after the rename.
            os.fsync = _Killer(kill_on_call=2)
        store = StateStore(root)
        store.transition(WP, new_state, "crash-injection", EVIDENCE)
        os._exit(0)
    _, status = os.waitpid(pid, 0)
    return status


def _assert_uncorrupted(root: Path, allowed: set[WorkPackageState]) -> WorkPackageState:
    """Verify the store is readable and internally consistent.

    Corruption here means any of: an unparseable document, a state outside the two values the
    interrupted transition could have left, or a state that disagrees with the last logged
    transition. The last is the one a two-file layout would fail.

    Args:
        root: Store directory.
        allowed: The states the store is permitted to be in.

    Returns:
        (WorkPackageState): The observed state.
    """
    path = root / "state.json"
    with path.open(encoding="utf-8") as handle:
        document = json.load(handle)
    assert set(document) == {"version", "states", "transitions"}

    store = StateStore(root)
    observed = store.state_of(WP)
    assert observed in allowed, f"state {observed} outside {allowed}"

    records = [record for record in store.transitions() if record.wp == WP]
    if records:
        assert records[-1].new_state is observed, "log and state disagree"
        for earlier, later in zip(records, records[1:], strict=False):
            assert earlier.new_state is later.previous_state, "log chain is broken"
    else:
        assert observed is WorkPackageState.NOT_STARTED
    return observed


def test_hundred_crashes_leave_zero_corruption(tmp_path: Path) -> None:
    """Acceptance ⑥ — corruption count must be exactly 0 across 100 injected crashes."""
    corrupted = 0
    completed = 0

    for iteration in range(CRASH_ITERATIONS):
        root = tmp_path / f"run{iteration}"
        store = StateStore(root)
        store.transition(WP, WorkPackageState.ACTIVE, "setup", EVIDENCE)

        crash_point = CRASH_POINTS[iteration % len(CRASH_POINTS)]
        _crash_in_child(root, crash_point, WorkPackageState.INTEGRATED)

        try:
            observed = _assert_uncorrupted(
                root, {WorkPackageState.ACTIVE, WorkPackageState.INTEGRATED}
            )
        except (AssertionError, ValueError, json.JSONDecodeError):
            corrupted += 1
            continue
        if observed is WorkPackageState.INTEGRATED:
            completed += 1

    assert corrupted == 0
    # The suite is only meaningful if the injection actually interrupts work: at least one crash
    # must have landed before the rename, and at least one after it.
    assert 0 < completed < CRASH_ITERATIONS


def _write_non_atomically(path: Path, payload: dict[str, object]) -> None:
    """Write the store document straight onto the target, in two flushed chunks.

    This is the implementation the atomic one replaces: no temp file, no rename, so a crash
    between the chunks leaves a truncated document on disk.

    Args:
        path: Destination document.
        payload: Document to persist.
    """
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    midpoint = len(text) // 2
    with path.open("w", encoding="utf-8") as handle:
        handle.write(text[:midpoint])
        handle.flush()
        os.fsync(handle.fileno())
        handle.write(text[midpoint:])
        handle.flush()
        os.fsync(handle.fileno())


def test_violation_fixture_non_atomic_writer_is_caught(tmp_path: Path) -> None:
    """The harness must go red on a non-atomic writer, or it proves nothing about the real one.

    Negative control for acceptance ⑥: same crash points, same verification, only the write
    strategy swapped. If this passes, the corruption check is not looking at anything.
    """
    import registry.state.store as store_module

    root = tmp_path / "nonatomic"
    store = StateStore(root)
    store.transition(WP, WorkPackageState.ACTIVE, "setup", EVIDENCE)

    pid = os.fork()
    if pid == 0:
        store_module._atomic_write_json = _write_non_atomically
        # Die at the first flush, with only half the document on the target file.
        os.fsync = _Killer(kill_on_call=1)
        StateStore(root).transition(WP, WorkPackageState.INTEGRATED, "crash", EVIDENCE)
        os._exit(0)
    os.waitpid(pid, 0)

    corrupted = False
    try:
        _assert_uncorrupted(root, {WorkPackageState.ACTIVE, WorkPackageState.INTEGRATED})
    except (AssertionError, ValueError, json.JSONDecodeError):
        corrupted = True
    assert corrupted, "non-atomic writer survived the crash check: the check is not checking"


def test_store_still_usable_after_a_crash(tmp_path: Path) -> None:
    """A child dying mid-transition must not wedge the store or strand its lock."""
    store = StateStore(tmp_path)
    store.transition(WP, WorkPackageState.ACTIVE, "setup", EVIDENCE)
    _crash_in_child(tmp_path, BEFORE_RENAME, WorkPackageState.INTEGRATED)

    assert store.state_of(WP) is WorkPackageState.ACTIVE
    record = store.transition(WP, WorkPackageState.INTEGRATED, "after-crash", EVIDENCE)
    assert record.new_state is WorkPackageState.INTEGRATED


def test_stray_temporary_file_is_never_read(tmp_path: Path) -> None:
    """A temp file left by a crash is inert: the store reads only the committed document."""
    store = StateStore(tmp_path)
    store.transition(WP, WorkPackageState.ACTIVE, "setup", EVIDENCE)
    stray = tmp_path / "state.json.tmp.999999"
    stray.write_text("{ this is not json", encoding="utf-8")

    assert store.state_of(WP) is WorkPackageState.ACTIVE
    assert len(store.transitions()) == 1
