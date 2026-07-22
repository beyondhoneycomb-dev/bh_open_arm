"""The joint jog producer — publish-only, no CAN handle (`WP-2A-01`).

`JointJogProducer` is a `Producer` (`backend.actuation.producer.Producer`): the
scheduler swaps it in and out through the atomic producer swap, and it publishes
targets into the Wave-1 `TargetMailbox`. It holds *only* the mailbox — no scheduler,
no CAN writer — so the single-CAN-writer invariant (`02a` §3.1 ①, I-1) is structural
here too: there is no attribute path from this producer to a bus handle, which
acceptance ① then confirms statically (`find_producer_can_access` finds zero CAN
symbols in this tree).

Division of labour with the interpolator: the interpolator (`interpolator.py`)
plans one jog into a time-stamped `JogTrajectory`; this producer emits it one
waypoint at a time through `publish(target, t_mono)`. Emitting waypoint-by-waypoint
rather than dumping the whole trajectory is required by the latest-wins mailbox — a
single slot keeps only the last publish — and is what lets a driver interleave a
publish per scheduler tick so one step becomes `hz × duration` emitted frames.
"""

from __future__ import annotations

from backend.actuation.mailbox import TargetMailbox, TimestampedTarget
from contracts.action import RequestedPositionAction


class JointJogProducer:
    """A swappable jog source whose only privilege is publishing to its mailbox.

    Ownership: holds the shared `TargetMailbox` and nothing else. It satisfies the
    `Producer` protocol (`producer_id`, `join`), so the scheduler drives it through
    the same atomic swap as any other producer; the swap is what keeps a mode change
    from ever interrupting the CAN tick (acceptance ③).
    """

    def __init__(self, producer_id: str, mailbox: TargetMailbox) -> None:
        """Bind a jog producer to the mailbox it publishes into.

        Args:
            producer_id: Stable identity for traces and swap accounting.
            mailbox: The one-slot, latest-wins channel to the scheduler.
        """
        self._producer_id = producer_id
        self._mailbox = mailbox
        self._joined = False

    @property
    def producer_id(self) -> str:
        """Stable identity used in traces and swap accounting.

        Returns:
            (str) This producer's id.
        """
        return self._producer_id

    @property
    def joined(self) -> bool:
        """Whether this producer has been joined (swapped out and released).

        Returns:
            (bool) True after `join`.
        """
        return self._joined

    def publish(self, target: RequestedPositionAction, t_mono: float) -> None:
        """Publish one position request stamped with the waypoint's monotonic time.

        Returns nothing and never blocks — it hands one `TimestampedTarget` to the
        latest-wins mailbox. The timestamp is supplied by the caller (the waypoint's
        `at`, read on the scheduler's clock) rather than sampled here, so an
        interpolated trajectory's timing is the trajectory's, not this call's.

        Args:
            target: The 16-dim bimanual position request to publish, degrees.
            t_mono: Monotonic time to stamp the target with, seconds.
        """
        self._mailbox.publish(TimestampedTarget(request=target, published_at=t_mono))

    def join(self) -> None:
        """Release the producer after a swap. Idempotent; a double join is not an error."""
        self._joined = True
