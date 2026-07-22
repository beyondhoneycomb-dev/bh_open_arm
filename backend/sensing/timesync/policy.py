"""The frozen `ApproximateTime` policy: slop, queue size, and the disabled fallbacks.

`02b` §6.1/§6.2 WP-3B-04 fixes three things this module is the body of:

- The matching tolerance `slop` and the per-stream buffer bound `queue_size` are
  configurable, but `slop` is *floored* at the exposure-phase upper bound — half a
  frame interval (`06` §2.6, FR-CAM-020). A slop below that floor would drop frames
  that are merely out of phase, not out of sync, so `for_fps` refuses it (acceptance
  ②). The floor is derived from the stream's fps, never a fixed 16.7 ms literal.
- `allow_headerless` and `sync_arrival_time` are the librealsense/`message_filters`
  fallbacks that match on *arrival* time. They are off by contract (acceptance
  frozen-interface row): arrival time is a receive stamp, and CTR-CAP pins matching
  to the grab-site `capture_ts`. The policy records them as fields so the pin is
  explicit and testable, and rejects turning either on.

`queue_size` defaults to the frozen `capture_match` queue capacity (`CTR-PRIM@v1`),
so the buffer bound and its COUNTED drop meaning come from the one queue definition
every capture consumer shares, not a number reinvented here.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.sensing.timesync.constants import NANOS_PER_SECOND
from contracts.capture.schema import CAPTURE_MATCH_QUEUE


class SyncPolicyError(ValueError):
    """Raised when a synchroniser policy violates the frozen WP-3B-04 contract."""


def slop_floor_ns(fps: int) -> int:
    """The smallest admissible matching slop for a stream at `fps`, in nanoseconds.

    Two un-hardware-synced cameras at `fps` can sit up to half a frame interval
    apart in exposure phase (`06` §2.6). Matching with a slop below that would drop
    frames that are only out of phase, so it is the floor, not a target.

    Args:
        fps: The stream frame rate; must be positive.

    Returns:
        (int) Half the frame interval in nanoseconds.

    Raises:
        SyncPolicyError: If `fps` is not positive.
    """
    if fps <= 0:
        raise SyncPolicyError(f"fps must be positive to derive a slop floor, got {fps}")
    return (NANOS_PER_SECOND // fps) // 2


def default_queue_size() -> int:
    """The default per-stream buffer bound: the frozen `capture_match` capacity.

    Returns:
        (int) `CTR-PRIM@v1`'s `capture_match` queue `bounded_capacity`.
    """
    return CAPTURE_MATCH_QUEUE.bounded_capacity


@dataclass(frozen=True)
class SyncPolicy:
    """The configuration one `synchronize` run reads.

    Attributes:
        slop_ns: The nearest-match tolerance; two frames pair only when their match
            timestamps sit within this many nanoseconds. Floored per fps by `for_fps`.
        queue_size: The per-stream buffer bound. A frame evicted from a full buffer
            before it matches is a COUNTED drop, never interpolated.
        allow_headerless: The arrival-time fallback for headerless messages. Off by
            contract; constructing it True is refused.
        sync_arrival_time: The arrival-time matching fallback. Off by contract;
            constructing it True is refused.
    """

    slop_ns: int
    queue_size: int
    allow_headerless: bool = False
    sync_arrival_time: bool = False

    def __post_init__(self) -> None:
        """Reject a non-positive tolerance, an empty buffer, or an enabled fallback."""
        if self.slop_ns <= 0:
            raise SyncPolicyError(f"slop_ns must be positive, got {self.slop_ns}")
        if self.queue_size < 1:
            raise SyncPolicyError(f"queue_size must be at least 1, got {self.queue_size}")
        if self.allow_headerless:
            raise SyncPolicyError(
                "allow_headerless matches on arrival time and is disabled by contract "
                "(WP-3B-04): matching is pinned to the grab-site capture_ts"
            )
        if self.sync_arrival_time:
            raise SyncPolicyError(
                "sync_arrival_time matches on arrival time and is disabled by contract "
                "(WP-3B-04): matching is pinned to the grab-site capture_ts"
            )

    @classmethod
    def for_fps(
        cls,
        fps: int,
        slop_ns: int | None = None,
        queue_size: int | None = None,
    ) -> SyncPolicy:
        """Build a policy for a stream at `fps`, enforcing the slop floor.

        A `slop_ns` of None takes the floor exactly; a value below the floor is
        refused (acceptance ②). A `queue_size` of None takes the frozen default.

        Args:
            fps: The common stream frame rate.
            slop_ns: The matching tolerance, or None to take the floor.
            queue_size: The buffer bound, or None to take the frozen default.

        Returns:
            (SyncPolicy) The validated policy.

        Raises:
            SyncPolicyError: If `slop_ns` is below the fps-derived floor.
        """
        floor = slop_floor_ns(fps)
        chosen_slop = floor if slop_ns is None else slop_ns
        if chosen_slop < floor:
            raise SyncPolicyError(
                f"slop_ns {chosen_slop} is below the {floor} ns half-frame phase floor for "
                f"{fps} fps; a slop under the phase bound drops out-of-phase frames (FR-CAM-020)"
            )
        return cls(
            slop_ns=chosen_slop,
            queue_size=default_queue_size() if queue_size is None else queue_size,
        )
