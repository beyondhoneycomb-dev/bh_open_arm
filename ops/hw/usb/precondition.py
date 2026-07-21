"""The measurement precondition: a measurement without the flock held is invalid.

`15` §2.10 M-1 makes exclusive single-process occupancy a *precondition* of the CAN
frequency measurement — SocketCAN offers no exclusive bind (`16` §10.1 / `15` §4
F-6), so the `WP-0B-01` cooperative `flock` is the only thing that guarantees no
second writer perturbed the bus during the sweep. A measurement taken without that
lock held is not merely lower quality; it is void, and `WP-0B-06`'s contract is that
its artifact publication is *refused* outright.

This module is that gate. It wraps the `WP-0B-01` `assert_lock_held` and captures,
at check time, the `lock_held=true` evidence the artifact is required to carry. It
is pure guard logic over the lock manager — no CAN stack, no hardware — which is why
the refusal path is the `WP-0B-06` acceptance that runs in full on this host.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass

from backend.can.lock.connect_guard import LockOrderingError, assert_lock_held
from backend.can.lock.manager import LockManager


class MeasurementRefusedError(RuntimeError):
    """A measurement or its artifact was attempted without the required flock held.

    Distinct from `LockOrderingError` (the connect-path ordering fault) so a caller
    can tell "you published without the lock" from "you connected without the lock",
    even though the underlying precondition is the same.
    """


@dataclass(frozen=True)
class LockHeldEvidence:
    """Proof, captured at check time, that this process held every measured channel.

    This is the `lock_held=true` evidence `WP-0B-06`'s contract requires on the
    artifact. It is a snapshot, not a live handle: it records that the lock *was*
    held when the measurement was cleared for publication, together with who held it.

    Attributes:
        lock_held: Always True — an instance is only ever constructed when the assert
            passed; a refusal raises instead of producing evidence.
        holder_pid: PID of the process that held the locks (this process).
        ifaces: The channels that were held, sorted.
        lock_paths: iface -> canonical lock-file path that was held.
    """

    lock_held: bool
    holder_pid: int
    ifaces: tuple[str, ...]
    lock_paths: dict[str, str]

    def as_dict(self) -> dict[str, object]:
        """Project to a JSON-serialisable mapping for the artifact.

        Returns:
            (dict[str, object]) The evidence as plain data.
        """
        return {
            "lock_held": self.lock_held,
            "holder_pid": self.holder_pid,
            "ifaces": list(self.ifaces),
            "lock_paths": dict(self.lock_paths),
        }


def require_lock_for_measurement(
    manager: LockManager,
    ifaces: Sequence[str],
) -> LockHeldEvidence:
    """Assert every measured channel is held by this process and return the evidence.

    This is the single entry point a measurement or publish path calls before it is
    allowed to proceed. On success it returns the `lock_held=true` evidence to stamp
    onto the artifact; on failure it raises `MeasurementRefusedError` and produces no
    evidence, so a caller that forgets to handle the failure cannot accidentally
    publish an unproven artifact.

    Args:
        manager: The `WP-0B-01` lock manager expected to hold the channels.
        ifaces: The channels the measurement covers; all must be held by `manager`.

    Returns:
        (LockHeldEvidence) Proof the lock was held, for the artifact.

    Raises:
        MeasurementRefusedError: If any channel is not held by this process.
    """
    ordered = tuple(sorted(ifaces))
    try:
        assert_lock_held(manager, ordered)
    except LockOrderingError as exc:
        raise MeasurementRefusedError(
            f"measurement refused: flock not held for all of {list(ordered)} "
            f"(15 §2.10 M-1 precondition; a lock-not-held measurement is void) — {exc}"
        ) from exc

    states = manager.lock_state(ordered)
    return LockHeldEvidence(
        lock_held=True,
        holder_pid=os.getpid(),
        ifaces=ordered,
        lock_paths={state.iface: state.lock_path for state in states},
    )
