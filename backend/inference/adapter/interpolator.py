"""The async-chunking buffers a backend switch must drain to residual 0 (`FR-INF-021`).

Two buffers sit between the policy and the mailbox on the async paths: the
`ActionChunkQueue` holds the actions of the current chunk waiting to be published,
and the `ChunkInterpolator` holds the intermediate targets bridging one action to
the next when the control tick is finer than the chunk step. `FR-INF-021` (SPINE
§2-2) requires that switching backend resets *both* to empty while the robot stays
connected — CG-4A-07e counts their residual after 100 switches and it must be 0
every time. Exposing `residual()` on each is what makes "reset" a measured fact
rather than a claim.

The interpolation itself is linear in joint-degree space: given the previously
published target and the next queued action, it lays down `steps` evenly-spaced
intermediate `RequestedPositionAction`s so the published stream is smooth at the
CAN tick rate without the policy having to emit at that rate.
"""

from __future__ import annotations

from collections import deque

from contracts.action import BIMANUAL_ACTION_DIM, RequestedPositionAction
from contracts.units import Deg


class ActionChunkQueue:
    """A FIFO of the current chunk's actions awaiting publication.

    Ownership: filled by the async producer when a chunk arrives, drained one action
    per consume tick by the engine, and cleared on a backend switch or episode reset.
    """

    def __init__(self) -> None:
        """Start with an empty queue."""
        self._queue: deque[RequestedPositionAction] = deque()

    def residual(self) -> int:
        """Number of actions still queued (`FR-INF-020` backlog, CG-4A-07e residual).

        Returns:
            (int) Queue size.
        """
        return len(self._queue)

    def push_chunk(self, actions: list[RequestedPositionAction]) -> None:
        """Append a freshly generated chunk's actions in order.

        Args:
            actions: The chunk's ordered position requests.
        """
        self._queue.extend(actions)

    def pop(self) -> RequestedPositionAction | None:
        """Remove and return the next queued action, or None when the queue is empty.

        Returns:
            (RequestedPositionAction | None) The next action, or None when starved.
        """
        if not self._queue:
            return None
        return self._queue.popleft()

    def clear(self) -> None:
        """Drop every queued action (backend switch / episode reset)."""
        self._queue.clear()


class ChunkInterpolator:
    """Linear interpolator laying intermediate targets between chunk actions.

    Ownership: loaded by the engine when it advances to a new chunk action, drained
    one intermediate per tick, and reset on a backend switch or episode reset.
    """

    def __init__(self) -> None:
        """Start with nothing to interpolate."""
        self._pending: deque[RequestedPositionAction] = deque()

    def residual(self) -> int:
        """Number of intermediate targets not yet emitted (CG-4A-07e residual).

        Returns:
            (int) Pending interpolation frames.
        """
        return len(self._pending)

    def load(
        self,
        previous: RequestedPositionAction,
        target: RequestedPositionAction,
        steps: int,
    ) -> None:
        """Lay down `steps` evenly-spaced targets from `previous` toward `target`.

        The final loaded target equals `target` exactly (fraction 1.0), so the stream
        arrives at the commanded action; the intermediates are the smoothing.

        Args:
            previous: The last published target (interpolation start).
            target: The next chunk action (interpolation end).
            steps: Number of intermediate frames to lay down; must be >= 1.

        Raises:
            ValueError: If `steps < 1`.
        """
        if steps < 1:
            raise ValueError(f"interpolation steps must be >= 1; got {steps}")
        for index in range(1, steps + 1):
            fraction = index / steps
            values = tuple(
                Deg(
                    previous.values[joint].value
                    + (target.values[joint].value - previous.values[joint].value) * fraction
                )
                for joint in range(BIMANUAL_ACTION_DIM)
            )
            self._pending.append(RequestedPositionAction(values=values))

    def emit(self) -> RequestedPositionAction | None:
        """Return the next intermediate target, or None when none remain.

        Returns:
            (RequestedPositionAction | None) The next interpolated target, or None.
        """
        if not self._pending:
            return None
        return self._pending.popleft()

    def reset(self) -> None:
        """Drop every pending intermediate (backend switch / episode reset)."""
        self._pending.clear()
