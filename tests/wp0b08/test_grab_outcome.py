"""A grab reports what the device could tell it, and the runner never invents the rest.

Two facts about a `cv2.VideoCapture` over V4L2, both measured on this rig, force this shape:

- **There is no device frame number.** `CAP_PROP_POS_FRAMES` reads `-1.0` on every grab of a
  live capture. So a real source has a frame that arrived and no number for it, and the old
  `grab() -> int | None` could not say that: `None` already meant "nothing arrived". Returning a
  counter of its own instead would be a sequence that can never show a gap — a device that cannot
  drop, which is not a device.
- **There is a device capture instant, and it is better than the host's.** `CAP_PROP_POS_MSEC`
  carries the V4L2 buffer timestamp on `CLOCK_MONOTONIC` — the moment the driver captured the
  frame, ahead of the moment this process got around to stamping it.

The second one decides the measurement rather than merely improving it. Polling slots in a fixed
order stamps the second slot a poll later than the first, every pass, so host stamps describe the
loop; folded through nearest-match against a 30 fps grid, that produced a pair spread of 0.022 ms
on this rig — **below the physical floor**, because `03` §5.9 fixes two cameras with no hardware
sync at up to half a frame apart (±16.7 ms) and nothing can be tighter than the thing it measures.
The driver stamps put the same pair at 8.7 ms, which is a number that can exist.
"""

from __future__ import annotations

import pytest

from backend.camera.capture_run import (
    CaptureRunError,
    GrabbedFrame,
    run_capture,
)

LEFT = "left_wrist"
RIGHT = "right_wrist"
TARGET_FPS = 30.0
PASS_INTERVAL_S = 1.0 / TARGET_FPS
PASSES = 10

# A device capture instant far from any host reading, so a test cannot pass by the two happening
# to agree. Absolute monotonic nanoseconds, which is what the V4L2 buffer timestamp is.
DEVICE_EPOCH_NS = 596_133_450_753_000
DEVICE_INTERVAL_NS = 33_400_000


class _Clock:
    """Simulated host time that only a grab advances."""

    def __init__(self) -> None:
        self.now = 0.0

    def read(self) -> float:
        """Read without spending."""
        return self.now

    def spend(self) -> None:
        """Advance by one frame interval, which is what a grab costs."""
        self.now += PASS_INTERVAL_S


class _CounterSource:
    """A source whose device exposes a frame counter and no clock."""

    def __init__(self, clock: _Clock) -> None:
        self._clock = clock
        self._number = 0

    def grab(self) -> GrabbedFrame | None:
        """Answer the next device number."""
        self._clock.spend()
        self._number += 1
        return GrabbedFrame(frame_number=self._number)


class _DriverClockSource:
    """A source whose device stamps each frame and exposes no counter — a `cv2` capture."""

    def __init__(self, clock: _Clock, offset_ns: int = 0) -> None:
        self._clock = clock
        self._offset_ns = offset_ns
        self._frames = 0

    def grab(self) -> GrabbedFrame | None:
        """Answer the driver's capture instant for this frame."""
        self._clock.spend()
        stamp = DEVICE_EPOCH_NS + self._offset_ns + self._frames * DEVICE_INTERVAL_NS
        self._frames += 1
        return GrabbedFrame(capture_ts_ns=stamp)


class _SilentSource:
    """A source whose camera answered nothing."""

    def __init__(self, clock: _Clock) -> None:
        self._clock = clock

    def grab(self) -> GrabbedFrame | None:
        """Answer nothing, having spent the attempt."""
        self._clock.spend()
        return None


def _fps_for(*slots: str) -> dict[str, float]:
    return dict.fromkeys(slots, TARGET_FPS)


def test_a_frame_with_no_device_number_still_counts_as_arrived() -> None:
    """The case the old return type could not express, and the only case a real camera has."""
    clock = _Clock()

    run = run_capture(
        sources={LEFT: _DriverClockSource(clock)},
        target_fps=_fps_for(LEFT),
        duration_s=PASSES * PASS_INTERVAL_S,
        clock=clock.read,
    )

    slot = run.slots[0]
    assert slot.received == PASSES
    assert slot.frame_numbers == ()


def test_a_silent_grab_is_still_a_drop() -> None:
    """Widening the arrival must not have widened away the absence."""
    clock = _Clock()

    run = run_capture(
        sources={LEFT: _SilentSource(clock)},
        target_fps=_fps_for(LEFT),
        duration_s=PASSES * PASS_INTERVAL_S,
        clock=clock.read,
    )

    assert run.slots[0].received == 0
    assert run.slots[0].capture_ts_ns == ()


def test_the_device_stamp_is_recorded_rather_than_the_host_reading() -> None:
    """When the device says when it captured, that is what the slop is computed from.

    The host reading is available and deliberately not used: it says when this loop looked, and
    on a fixed-order poll the second slot is always looked at a poll later than the first.
    """
    clock = _Clock()

    run = run_capture(
        sources={LEFT: _DriverClockSource(clock)},
        target_fps=_fps_for(LEFT),
        duration_s=PASSES * PASS_INTERVAL_S,
        clock=clock.read,
    )

    stamps = run.slots[0].capture_ts_ns
    assert stamps[0] == 0
    assert [b - a for a, b in zip(stamps, stamps[1:], strict=False)] == [DEVICE_INTERVAL_NS] * (
        len(stamps) - 1
    )


def test_two_device_clocked_slots_keep_the_offset_between_them() -> None:
    """Rebasing may not be per-slot: the offset between two cameras IS the measurement.

    Subtracting each slot's own first stamp would put both at zero and report a pair that is
    perfectly in phase, whatever the cameras did.
    """
    clock = _Clock()
    offset_ns = 7_000_000

    run = run_capture(
        sources={
            LEFT: _DriverClockSource(clock),
            RIGHT: _DriverClockSource(clock, offset_ns=offset_ns),
        },
        target_fps=_fps_for(LEFT, RIGHT),
        duration_s=PASSES * PASS_INTERVAL_S,
        clock=clock.read,
    )

    left, right = run.slots
    assert right.capture_ts_ns[0] - left.capture_ts_ns[0] == offset_ns


def test_a_run_mixing_device_clocked_and_host_clocked_slots_is_refused() -> None:
    """Two time bases in one document make the spread between them arithmetic on nothing.

    Refused rather than reported, because the number it would produce is shaped like a slop and
    means nothing — and the run it would waste is ten minutes long.
    """
    clock = _Clock()

    with pytest.raises(CaptureRunError, match="time base"):
        run_capture(
            sources={LEFT: _DriverClockSource(clock), RIGHT: _CounterSource(clock)},
            target_fps=_fps_for(LEFT, RIGHT),
            duration_s=PASSES * PASS_INTERVAL_S,
            clock=clock.read,
        )
