"""The CAN writer handle — the one object a producer must never reach.

`CanWriter` is the type-level chokepoint behind the single-CAN-writer invariant
(`02a` §3.1 ①). The scheduler holds the only reference to one; producers hold a
mailbox instead. The static checker (`backend.actuation.staticcheck`) then makes
"a producer reaching a CAN handle" a compile-stage failure (acceptance ⑥) by
rejecting any reference to this module's symbols from outside `backend/actuation`.

The single method is `mit_control_batch`, the batched MIT-frame write that mirrors
the upstream `DamiaoMotorsBus._mit_control_batch` (`12` §2.7). It is the *only*
way torque reaches the bus between torque-on and torque-off. Note what is absent:
there is no `disable_torque`. The stop path is a hold frame, never a torque cut
(`04` NFR-MAN-002), and acceptance ⑦ checks statically that the symbol never
appears in this tree.

`FakeCanWriter` is the AI-offline backend: it records every frame and supports
fault injection (a write can be told to raise, standing in for a bus fault) so the
scheduler can be exercised for a million ticks with no real hardware.
"""

from __future__ import annotations

from typing import Protocol

from contracts.action import ExecutedMitCommand

# One MIT command per bimanual joint (`10` §2.3: 8 per arm, two arms). The batch
# the CAN writer takes is always this wide.
MIT_BATCH_WIDTH = 16


class CanBusFaultError(Exception):
    """A simulated bus write fault, injected by the fake backend."""


class CanWriter(Protocol):
    """The sole torque-carrying handle to the CAN bus.

    Held only by the scheduler. It sends a hold-or-command MIT frame and counts
    the frames it actually sent; there is deliberately no method that cuts torque
    (`04` NFR-MAN-002). `write_count` is what makes the scheduler's per-tick
    "exactly one CAN write" guard real: the scheduler reads the writer's own
    successful-send counter around the call, so a writer that silently drops or
    doubles a frame is caught rather than trusted.
    """

    @property
    def write_count(self) -> int:
        """Total frames the writer has actually sent since construction.

        Returns:
            (int) Cumulative successful `mit_control_batch` calls.
        """
        ...

    def mit_control_batch(self, batch: tuple[ExecutedMitCommand, ...]) -> None:
        """Write one batched MIT frame to the bus.

        Args:
            batch: One `ExecutedMitCommand` per joint, length `MIT_BATCH_WIDTH`.
        """
        ...


class FakeCanWriter:
    """A CAN writer that records frames and can be told to fault, for AI-offline runs.

    Ownership: created by the harness, handed to the scheduler, never to a
    producer. It is the observable end of the spine — the trace proves *decisions*,
    this proves the *sends* those decisions caused.
    """

    def __init__(self) -> None:
        """Create a fake writer with an empty frame log and no injected fault."""
        self._write_count = 0
        self._last_batch: tuple[ExecutedMitCommand, ...] | None = None
        self._fault_armed = False

    @property
    def write_count(self) -> int:
        """Total number of frames written since construction.

        Returns:
            (int) Cumulative successful `mit_control_batch` calls.
        """
        return self._write_count

    @property
    def last_batch(self) -> tuple[ExecutedMitCommand, ...] | None:
        """The most recent batch written, or None before the first write.

        Returns:
            (tuple[ExecutedMitCommand, ...] | None) Last frame sent.
        """
        return self._last_batch

    def arm_fault(self) -> None:
        """Make the next `mit_control_batch` raise `CanBusFaultError`, once."""
        self._fault_armed = True

    def mit_control_batch(self, batch: tuple[ExecutedMitCommand, ...]) -> None:
        """Record a batched MIT frame, or raise if a fault is armed.

        Args:
            batch: One `ExecutedMitCommand` per joint, length `MIT_BATCH_WIDTH`.

        Raises:
            ValueError: If the batch is not `MIT_BATCH_WIDTH` wide.
            CanBusFaultError: If a fault was armed; the arm is cleared as it fires.
        """
        if len(batch) != MIT_BATCH_WIDTH:
            raise ValueError(f"MIT batch must be {MIT_BATCH_WIDTH} wide, got {len(batch)}")
        if self._fault_armed:
            self._fault_armed = False
            raise CanBusFaultError("injected CAN bus write fault")
        self._write_count += 1
        self._last_batch = batch
