"""The timed unit the synchroniser pairs, and the basis its match timestamp uses.

`02b` §6.2 WP-3B-04 fixes the matching basis: the device *sensor* timestamp when the
hardware exposes one, otherwise the host grab-time `capture_ts`. Arrival time is
never a basis — a receive stamp erases the exposure phase the whole sidecar exists to
preserve (CTR-CAP grab-site pin), which is why the arrival-time fallbacks are off in
`SyncPolicy`. `match_timestamp` is the single place that basis is decided; the
synchroniser reads only `TimedFrame.match_ts_ns` and never re-derives it.

`match_ts_ns` and `capture_ts_ns` are kept apart on purpose: matching happens on the
chosen basis, but the frame's real grab instant is always preserved beside it so the
host↔sensor offset stays auditable (`CTR-CAP@v1` parallel-preservation rule).
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.sensing.timesync.policy import SyncPolicy
from contracts.capture.schema import CameraSlotKey, SlotCapture


@dataclass(frozen=True)
class TimedFrame:
    """One frame as the synchroniser sees it: its slot, index and two timestamps.

    Attributes:
        slot: The camera slot, a `CTR-PRIM@v1` `CameraSlotKey`.
        frame_index: The 0-based frame position, the sidecar/dataset join key.
        match_ts_ns: The timestamp matching runs on — sensor when available, else the
            grab-time capture_ts (see `match_timestamp`).
        capture_ts_ns: The grab-time capture instant, preserved regardless of basis.
    """

    slot: CameraSlotKey
    frame_index: int
    match_ts_ns: int
    capture_ts_ns: int

    def __post_init__(self) -> None:
        """Reject a negative frame index."""
        if self.frame_index < 0:
            raise ValueError(f"frame_index must be >= 0, got {self.frame_index}")


def match_timestamp(capture: SlotCapture, policy: SyncPolicy) -> int:
    """The timestamp the synchroniser matches this capture on.

    Basis: the device sensor clock when the capture carries one, else the host
    grab-time capture_ts. `policy` is taken so the disabled arrival-time fallbacks are
    honoured at the one decision point; a policy with either enabled cannot be
    constructed, so this only ever returns a grab-anchored basis.

    Args:
        capture: The slot's per-frame capture record (`CTR-CAP@v1`).
        policy: The active sync policy (its fallbacks are off by contract).

    Returns:
        (int) The sensor timestamp in nanoseconds when present, else the capture_ts.
    """
    _ = policy  # the arrival-time fallbacks are refused at policy construction
    if capture.sensor is not None and capture.sensor.sensor_ts_ns is not None:
        return capture.sensor.sensor_ts_ns
    return capture.capture_ts.mono_ns


def timed_from_capture(
    slot: CameraSlotKey,
    frame_index: int,
    capture: SlotCapture,
    policy: SyncPolicy,
) -> TimedFrame:
    """Build a `TimedFrame` from a `CTR-CAP@v1` slot capture under a policy.

    Args:
        slot: The camera slot the capture belongs to.
        frame_index: The frame's 0-based index.
        capture: The slot's capture record.
        policy: The active sync policy.

    Returns:
        (TimedFrame) The frame with its basis-selected match timestamp and its
            preserved grab instant.
    """
    return TimedFrame(
        slot=slot,
        frame_index=frame_index,
        match_ts_ns=match_timestamp(capture, policy),
        capture_ts_ns=capture.capture_ts.mono_ns,
    )
