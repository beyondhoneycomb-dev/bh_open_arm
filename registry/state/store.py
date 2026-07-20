"""Durable work-package state store with atomic transitions and a single writer.

Structural rationale for the single-document layout: states and the transition log live in ONE
JSON file rewritten as a unit. Splitting them across two files would make every commit a
two-file update, and a crash landing between the two would leave a logged transition that never
happened (or a state change with no evidence line). Holding both in one atomically replaced
document makes that skew unrepresentable, which is what acceptance ⑥ (`02a` §-2.3 WP-BOOT-04)
asks for. The cost is rewriting the whole document per transition; at 177 work packages that is
irrelevant.

Concurrency: every mutation is serialised by an exclusive `flock` on a sibling lock file, and the
current state is re-read *inside* the lock. Two workflows racing to activate the same package
therefore resolve to one winner, because the loser observes ACTIVE and `active -> active` is not
a legal transition.
"""

from __future__ import annotations

import fcntl
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from registry.state.model import (
    CANCELLABLE_STATES,
    IllegalTransitionError,
    TransitionRecord,
    WorkPackageState,
    is_legal,
)

STORE_FILENAME = "state.json"
LOCK_FILENAME = "state.lock"
STORE_VERSION = 1


class StateStoreError(Exception):
    """Raised when the store is asked for something structurally impossible."""


def _atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    """Replace a JSON file atomically.

    Writes a sibling temporary file, flushes it to stable storage, then renames it over the
    target. `os.replace` is atomic within a filesystem, so a crash at any point leaves either the
    complete previous document or the complete new one. The parent directory is fsynced too,
    otherwise the rename itself may not survive a power loss.

    Args:
        path: Final destination of the document.
        payload: JSON-serialisable document to persist.
    """
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=1, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    # Kept as the os-level call rather than Path.replace: this is the exact primitive whose
    # atomicity the whole design rests on, and the crash harness interposes on it by name.
    os.replace(tmp, path)  # noqa: PTH105
    dir_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


class StateStore:
    """Per-work-package state plus an append-only transition log.

    Ownership: this store is the only writer of the workflow state axis. The latch path does not
    live here — it lives in `ops/cancel/` and is invoked by the cancellation executor.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.path = root / STORE_FILENAME
        self.lock_path = root / LOCK_FILENAME
        root.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _exclusive(self) -> Iterator[None]:
        """Hold an exclusive cross-process lock for the duration of a mutation.

        Yields:
            (None): Control, with the lock held.
        """
        with self.lock_path.open("w") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _read(self) -> dict[str, object]:
        """Load the store document, tolerating a store that does not exist yet.

        Returns:
            (dict[str, object]): The document, or an empty one on first use.
        """
        if not self.path.exists():
            return {"version": STORE_VERSION, "states": {}, "transitions": []}
        with self.path.open(encoding="utf-8") as handle:
            document: dict[str, object] = json.load(handle)
        return document

    def state_of(self, wp: str) -> WorkPackageState:
        """Report the current state of a work package.

        Args:
            wp: Work package id.

        Returns:
            (WorkPackageState): Recorded state, or NOT_STARTED when the package has no record.
        """
        states = self._states(self._read())
        return WorkPackageState(states.get(wp, WorkPackageState.NOT_STARTED.value))

    def all_states(self) -> dict[str, WorkPackageState]:
        """Report every recorded state.

        Returns:
            (dict[str, WorkPackageState]): Package id to state, for packages with a record.
        """
        states = self._states(self._read())
        return {wp: WorkPackageState(value) for wp, value in states.items()}

    def transitions(self) -> list[TransitionRecord]:
        """Read the transition log in commit order.

        Returns:
            (list[TransitionRecord]): Every committed transition, oldest first.
        """
        raw = self._read().get("transitions", [])
        if not isinstance(raw, list):
            raise StateStoreError(f"{self.path}: 'transitions' is not a list")
        return [TransitionRecord.from_json(item) for item in raw]

    def transition(
        self,
        wp: str,
        new_state: WorkPackageState,
        trigger: str,
        evidence_hash: str,
    ) -> TransitionRecord:
        """Move a work package to a new state, atomically and under the store lock.

        Args:
            wp: Work package id.
            new_state: Requested state.
            trigger: What caused the transition (gate id, operator action, closure trigger).
            evidence_hash: Hash of the evidence backing the transition.

        Returns:
            (TransitionRecord): The committed record.

        Raises:
            IllegalTransitionError: The observed previous state cannot reach `new_state`. A
                concurrency loser surfaces here, having observed the winner's state.
            StateStoreError: `trigger` or `evidence_hash` is empty. An unevidenced transition is
                exactly the "declaration without enforcement" this bootstrap exists to remove.
        """
        if not trigger:
            raise StateStoreError(f"{wp}: transition requires a trigger")
        if not evidence_hash:
            raise StateStoreError(f"{wp}: transition requires an evidence hash")

        with self._exclusive():
            document = self._read()
            states = self._states(document)
            previous = WorkPackageState(states.get(wp, WorkPackageState.NOT_STARTED.value))
            if not is_legal(previous, new_state):
                raise IllegalTransitionError(wp, previous, new_state)

            record = TransitionRecord(
                wp=wp,
                previous_state=previous,
                new_state=new_state,
                trigger=trigger,
                evidence_hash=evidence_hash,
            )
            states[wp] = new_state.value
            log = document.get("transitions", [])
            if not isinstance(log, list):
                raise StateStoreError(f"{self.path}: 'transitions' is not a list")
            log.append(record.to_json())
            _atomic_write_json(
                self.path,
                {"version": STORE_VERSION, "states": states, "transitions": log},
            )
            return record

    def cancellable(self, wps: list[str]) -> list[str]:
        """Select the packages whose output is not yet integrated.

        Integrated packages are excluded on purpose: merged work is undone by a named revert WP,
        never by cancellation (`05` §5.2 P-4).

        Args:
            wps: Candidate package ids, typically a descendant closure.

        Returns:
            (list[str]): Cancellable ids, in the order given.
        """
        states = self.all_states()
        return [
            wp for wp in wps if states.get(wp, WorkPackageState.NOT_STARTED) in CANCELLABLE_STATES
        ]

    @staticmethod
    def _states(document: dict[str, object]) -> dict[str, str]:
        """Extract the state map from a store document.

        Args:
            document: Loaded store document.

        Returns:
            (dict[str, str]): Package id to raw state value.
        """
        states = document.get("states", {})
        if not isinstance(states, dict):
            raise StateStoreError("store document: 'states' is not a mapping")
        return states
