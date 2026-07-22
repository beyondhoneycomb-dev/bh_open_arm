"""The `ApproximateTime` nearest-match synchroniser — pair within slop or drop.

`02b` §6.1/§6.2 WP-3B-04: pair frames across camera slots by nearest capture time
within `slop`, and when a slot has no frame within slop of the pivot, **drop** — a
match miss produces no output row. The one rule the module protects is that a drop
is a drop: there is no interpolation and no duplication, because a fabricated frame
is the defect the acceptance test hunts for (`02b` §6.2 WP-3B-04 ①). Two invariants
in the code make the ban structural:

- Every frame in an emitted `MatchedSet` is a real input frame the run was given;
  the set carries each frame's own timestamps and synthesises none.
- A frame is removed from its buffer the moment it enters a set, so no frame can
  appear in two sets — the "no duplication" half of the ban.

The algorithm is the bounded-queue pivot form of `message_filters::ApproximateTime`:
frames are fed in global capture-time order into per-slot buffers bounded by
`queue_size`; at each step the latest buffer head is the pivot, each slot contributes
the buffered frame nearest the pivot, and the set is emitted only when all of them
lie within `slop`. A frame that ages out of a full buffer, an unmatchable head, and
any frame left over when the feed ends are all COUNTED drops — the classification
`CTR-CAP@v1` fixes for a capture match, not one invented here.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from backend.sensing.timesync.frame import TimedFrame
from backend.sensing.timesync.policy import SyncPolicy
from contracts.capture.schema import (
    CameraSlotKey,
    DropClassification,
    capture_match_drop_classification,
)


@dataclass(frozen=True)
class MatchedSet:
    """One synchronised set: exactly one real frame per slot, within slop.

    The set never fabricates a joint timestamp — each frame keeps its own
    `match_ts_ns`/`capture_ts_ns`, and `spread_ns` reports how far apart the members
    actually sit so a consumer can see the residual phase, not a smoothed-over one.

    Attributes:
        frames: The matched frame for each slot.
    """

    frames: Mapping[CameraSlotKey, TimedFrame]

    def spread_ns(self) -> int:
        """The largest match-timestamp gap within the set, in nanoseconds.

        Returns:
            (int) `max - min` of the members' match timestamps.
        """
        stamps = [frame.match_ts_ns for frame in self.frames.values()]
        return max(stamps) - min(stamps)


@dataclass(frozen=True)
class DropTally:
    """The per-slot count of frames dropped by matching, with the shared meaning.

    Attributes:
        per_slot: Dropped-frame count keyed by slot.
        classification: The `CTR-CAP@v1` meaning of a capture-match drop — COUNTED,
            not a defect and not a normal latest-wins shed.
    """

    per_slot: Mapping[CameraSlotKey, int]
    classification: DropClassification

    @property
    def total(self) -> int:
        """The total dropped-frame count across all slots."""
        return sum(self.per_slot.values())


@dataclass(frozen=True)
class SyncResult:
    """The outcome of one `synchronize` run: the sets that matched and what dropped.

    The accounting closes: every input frame is either a member of exactly one
    matched set or counted once in `dropped`, so `matched_frame_count + dropped.total`
    equals the number of frames fed in.

    Attributes:
        matched: The synchronised sets, in emission (ascending pivot) order.
        dropped: The per-slot drop tally.
    """

    matched: tuple[MatchedSet, ...]
    dropped: DropTally

    @property
    def matched_frame_count(self) -> int:
        """The number of input frames that landed in a matched set."""
        return sum(len(one.frames) for one in self.matched)


def _nearest_to(buffer: deque[TimedFrame], pivot_ts: int) -> TimedFrame:
    """Return the buffered frame closest to `pivot_ts`, ties broken by frame index.

    A named scan rather than a `min` with a pivot-capturing lambda: the pivot changes
    every drain step, and a closure over a loop variable is exactly the binding hazard
    to avoid here.
    """
    best = buffer[0]
    best_key = (abs(best.match_ts_ns - pivot_ts), best.frame_index)
    for frame in buffer:
        key = (abs(frame.match_ts_ns - pivot_ts), frame.frame_index)
        if key < best_key:
            best, best_key = frame, key
    return best


def _drain(
    buffers: dict[CameraSlotKey, deque[TimedFrame]],
    drops: dict[CameraSlotKey, int],
    matched: list[MatchedSet],
    slots: Sequence[CameraSlotKey],
    slop_ns: int,
) -> None:
    """Emit every set the current buffers can form, dropping what cannot match.

    Each iteration makes progress — an emit removes at least one frame per slot, a
    miss removes one head — so the loop terminates when any slot empties. Frames
    older than a matched frame are shed as drops: a later pivot only moves forward,
    so they can never match anything still to come.
    """
    while all(buffers[slot] for slot in slots):
        pivot_ts = max(buffers[slot][0].match_ts_ns for slot in slots)
        chosen = {slot: _nearest_to(buffers[slot], pivot_ts) for slot in slots}
        stamps = [frame.match_ts_ns for frame in chosen.values()]
        if max(stamps) - min(stamps) <= slop_ns:
            matched.append(MatchedSet(frames=chosen))
            for slot in slots:
                picked = chosen[slot]
                while buffers[slot] and buffers[slot][0].match_ts_ns <= picked.match_ts_ns:
                    popped = buffers[slot].popleft()
                    if popped is not picked:
                        drops[slot] += 1
        else:
            oldest = min(slots, key=lambda slot: (buffers[slot][0].match_ts_ns, slot.value))
            buffers[oldest].popleft()
            drops[oldest] += 1


def synchronize(
    streams: Mapping[CameraSlotKey, Sequence[TimedFrame]],
    policy: SyncPolicy,
) -> SyncResult:
    """Pair frames across slots by nearest capture time within slop; drop on miss.

    Args:
        streams: Per-slot frame sequences. At least two slots are required — a set is
            a cross-slot object. Each slot's frames may be in any order; they are
            ordered by match timestamp internally.
        policy: The slop and buffer bound (its arrival-time fallbacks are off).

    Returns:
        (SyncResult) The matched sets and the per-slot drop tally, whose counts plus
            the matched frames account for every input frame exactly once.

    Raises:
        ValueError: If fewer than two slots are supplied.
    """
    slots = sorted(streams, key=lambda slot: slot.value)
    if len(slots) < 2:
        raise ValueError("time synchronisation needs at least two camera slots")

    buffers: dict[CameraSlotKey, deque[TimedFrame]] = {slot: deque() for slot in slots}
    drops: dict[CameraSlotKey, int] = dict.fromkeys(slots, 0)
    matched: list[MatchedSet] = []

    # Feed in global capture-time order so the pivot only advances; ties break by slot
    # so a run is deterministic. Overflow of a full buffer sheds its oldest frame — the
    # bounded-queue drop that gives queue_size teeth under jitter.
    events = sorted(
        ((frame.match_ts_ns, slot, frame) for slot in slots for frame in streams[slot]),
        key=lambda event: (event[0], event[1].value),
    )
    for _ts, slot, frame in events:
        buffer = buffers[slot]
        if len(buffer) >= policy.queue_size:
            buffer.popleft()
            drops[slot] += 1
        buffer.append(frame)
        _drain(buffers, drops, matched, slots, policy.slop_ns)

    # The feed is finite: any frame still buffered has no future partner, so it is a
    # counted drop rather than a silently held frame.
    for slot in slots:
        drops[slot] += len(buffers[slot])
        buffers[slot].clear()

    return SyncResult(
        matched=tuple(matched),
        dropped=DropTally(per_slot=drops, classification=capture_match_drop_classification()),
    )
