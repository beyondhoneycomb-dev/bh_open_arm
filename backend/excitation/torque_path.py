"""The `FR-MOT-058` torque command path the injection harness requires (`WP-2B-06`).

`02b` §2.3 ④ makes the torque command path the hard precondition of injection: without
a way to apply `τ`, an identification trajectory cannot be commanded. This module names
that path as the narrow interface the harness consumes — a sink that accepts a per-index
MIT command carrying feed-forward torque — and nothing more.

The concrete path is `FR-MOT-058`'s `send_action` bypass that routes feed-forward torque
into the emitted MIT frame through the single CAN writer (`03` FR-MOT-058, the scheduler
mailbox's `feedforward_torque`). That path is torque-ON hardware and is **not** built or
run on this host; it lives behind the single writer (`backend.actuation`) this package
must not touch. The harness therefore holds this interface, an implementation of it is
supplied by whoever wires the real path, and the deferred on-arm injection is the only
thing that needs the real one — every offline test drives a recording double instead.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class TorqueCommand:
    """One index's MIT command: target state plus the feed-forward torque to apply.

    Attributes:
        index: The trajectory index this command carries, so a recorded stream can be
            aligned to the trajectory and to any abort index.
        positions_rad: Per-joint target positions, radians (v2 convention).
        velocities_rad_s: Per-joint target velocities, radians/second.
        feedforward_torque_nm: Per-joint feed-forward torque, newton-metres — the gravity
            hold plus any excitation torque the harness composes. On a brakeless arm this
            is what keeps the arm from sagging while the exciting motion rides on top.
    """

    index: int
    positions_rad: tuple[float, ...]
    velocities_rad_s: tuple[float, ...]
    feedforward_torque_nm: tuple[float, ...]


@runtime_checkable
class TorqueCommandPath(Protocol):
    """A sink that applies a per-index MIT torque command on the real arm.

    The real implementation is `FR-MOT-058`'s torque path through the single CAN writer;
    the harness depends only on this method so it can be exercised against a recording
    double offline while the torque-ON path stays deferred.
    """

    def send(self, command: TorqueCommand) -> None:
        """Apply one torque command to the arm.

        Args:
            command: The per-index MIT command to emit.
        """
        ...


def torque_widths_match(command: TorqueCommand, joint_count: int) -> bool:
    """Report whether a command's three per-joint vectors all have `joint_count` entries.

    A width mismatch means the command was assembled against a different joint layout
    than the trajectory, which the harness treats as a wiring fault rather than sending.

    Args:
        command: The command to check.
        joint_count: The expected per-joint vector width.

    Returns:
        (bool) True when all three vectors have `joint_count` entries.
    """
    vectors: tuple[Sequence[float], ...] = (
        command.positions_rad,
        command.velocities_rad_s,
        command.feedforward_torque_nm,
    )
    return all(len(vector) == joint_count for vector in vectors)
