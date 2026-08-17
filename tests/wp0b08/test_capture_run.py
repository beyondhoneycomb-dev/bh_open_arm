"""The capture runner: what it records, what it refuses, and what it deliberately does not write.

No camera is opened. The frame source is a Protocol and the clock is injected, so the loop, the
timestamping and the accounting are the same ones a rig run uses and only the bytes differ — which
is the point, because the numbers this produces are what `PG-CAM-001` ③ and ④ are judged on and a
runner tested only against hardware could not be tested at all before the hardware existed.

The assertions that matter most are the omissions. A grab that returns nothing must leave a hole
in both the count and the sequence, because that hole IS the drop; anything substituted there
makes the drop rate describe this module instead of the cameras.
"""

from __future__ import annotations

import json

import pytest

from backend.camera.capture_run import (
    NS_PER_SECOND,
    CaptureRunError,
    GrabbedFrame,
    run_capture,
    slot_order_is_stable,
)
from backend.camera.droprate import compute_drop
from backend.camera.reverify import CAPTURE_TS_FILENAME, FRAMES_FILENAME
from backend.camera.syncslop import build_slop_reports

LEFT = "left_wrist"
RIGHT = "right_wrist"
TARGET_FPS = 30.0

# One pass per simulated frame interval, so a run of N passes is N frames at the target rate.
PASS_INTERVAL_S = 1.0 / TARGET_FPS
PASSES = 20


class _FakeTime:
    """Simulated time that only the work advances.

    Modelled on where the seconds actually go. `perf_counter` does not make time pass, so a
    double whose clock advanced per read would make the run's arithmetic depend on how many
    times it happened to look at the clock — which is a property of the loop's shape, not of the
    cameras. Here `grab` spends one frame interval, exactly as a camera does, and reads are free.
    """

    def __init__(self, step_s: float = PASS_INTERVAL_S) -> None:
        self.step_s = step_s
        self.now = 0.0

    def read(self) -> float:
        """Read the clock without spending anything."""
        return self.now

    def spend_one_frame(self) -> None:
        """Advance by one frame interval, which is what a grab costs."""
        self.now += self.step_s


class _Source:
    """A frame source that spends a frame interval per grab and drops on chosen passes."""

    def __init__(self, time_source: _FakeTime, drop_on: frozenset[int] = frozenset()) -> None:
        self._time = time_source
        self._drop_on = drop_on
        self._calls = 0
        self._number = 0

    def grab(self) -> GrabbedFrame | None:
        """Spend one frame interval, then answer the next device number or nothing on a drop.

        This models a device that numbers its frames and never loses one itself: the drop
        happens at the reader, so the counter stays contiguous while the arrival count falls
        short. A `cv2` capture is the other shape — it numbers nothing — and
        `test_grab_outcome.py` is where that one is pinned.
        """
        call = self._calls
        self._calls += 1
        self._time.spend_one_frame()
        if call in self._drop_on:
            return None
        self._number += 1
        return GrabbedFrame(frame_number=self._number)


def _fps_for(*slots: str) -> dict[str, float]:
    return dict.fromkeys(slots, TARGET_FPS)


def test_a_run_records_one_timestamp_per_frame_that_arrived() -> None:
    """The count is the arrivals, not the attempts."""
    clock = _FakeTime()
    run = run_capture(
        sources={LEFT: _Source(clock)},
        target_fps=_fps_for(LEFT),
        duration_s=PASSES * PASS_INTERVAL_S,
        clock=clock.read,
    )

    assert len(run.slots) == 1
    assert run.slots[0].received == len(run.slots[0].capture_ts_ns)
    assert run.slots[0].received > 0


def test_a_dropped_grab_leaves_a_hole_rather_than_a_substitute() -> None:
    """The hole IS the drop. A synthesised timestamp would hide it in both outputs."""
    dropped = frozenset({2, 5, 9})
    clock = _FakeTime()
    run = run_capture(
        sources={LEFT: _Source(clock, drop_on=dropped)},
        target_fps=_fps_for(LEFT),
        duration_s=PASSES * PASS_INTERVAL_S,
        clock=clock.read,
    )
    slot = run.slots[0]

    assert slot.received == len(slot.frame_numbers)
    assert len(set(slot.frame_numbers)) == len(slot.frame_numbers)
    # The device numbers stay contiguous — the device did not produce the dropped frames — while
    # the arrival count falls short of the passes, which is what `compute_drop` reads.
    assert slot.frame_numbers == tuple(range(1, slot.received + 1))


def test_the_drop_computer_reads_this_run_and_reports_a_loss() -> None:
    """End to end into the calculator the gate uses, so the shape is proved by its consumer."""
    dropped = frozenset(range(0, PASSES, 4))
    clock = _FakeTime()
    run = run_capture(
        sources={LEFT: _Source(clock, drop_on=dropped)},
        target_fps=_fps_for(LEFT),
        duration_s=PASSES * PASS_INTERVAL_S,
        clock=clock.read,
    )
    slot = run.slots[0]

    report = compute_drop(
        target_fps=slot.target_fps,
        duration_s=run.duration_s,
        received_count=slot.received,
        frame_numbers=list(slot.frame_numbers),
    )

    assert report.drop_fraction > 0.0


def test_a_clean_run_reports_no_loss() -> None:
    """The negative, so the drop reading is not something every run produces."""
    clock = _FakeTime()
    run = run_capture(
        sources={LEFT: _Source(clock)},
        target_fps=_fps_for(LEFT),
        duration_s=PASSES * PASS_INTERVAL_S,
        clock=clock.read,
    )
    slot = run.slots[0]

    report = compute_drop(
        target_fps=slot.target_fps,
        duration_s=run.duration_s,
        received_count=slot.received,
        frame_numbers=list(slot.frame_numbers),
    )

    assert report.drop_fraction == pytest.approx(0.0, abs=1.0 / PASSES)


def test_two_slots_produce_a_pair_the_slop_reporter_accepts() -> None:
    """Acceptance ③ comes out of the same capture as ④; this proves the handoff."""
    clock = _FakeTime()
    run = run_capture(
        sources={LEFT: _Source(clock), RIGHT: _Source(clock)},
        target_fps=_fps_for(LEFT, RIGHT),
        duration_s=PASSES * PASS_INTERVAL_S,
        clock=clock.read,
    )

    reports = build_slop_reports(run.capture_ts_document())

    assert len(reports) == 1
    assert reports[0].pair == (LEFT, RIGHT)
    assert reports[0].q99_ms >= 0.0


def test_the_window_recorded_is_the_one_that_elapsed() -> None:
    """A run cut short must be judged against the time it ran, not the time it asked for.

    Using the requested duration would count every unrun second as dropped frames, which turns
    an operator pressing stop into a camera fault.
    """
    clock = _FakeTime()
    run = run_capture(
        sources={LEFT: _Source(clock)},
        target_fps=_fps_for(LEFT),
        duration_s=PASSES * PASS_INTERVAL_S,
        clock=clock.read,
    )

    # Compared against the last timestamp rather than against the request. Under a double whose
    # grabs land exactly on the frame grid the two happen to agree, so asserting they differ
    # would pass for the wrong reason; what identifies a measured value is that it matches the
    # capture — a run whose window was echoed back would still say 0.667 s with no frames in it.
    stamps = run.slots[0].capture_ts_ns
    assert run.duration_s == pytest.approx(stamps[-1] / NS_PER_SECOND)
    assert run.frames_document()[LEFT]["duration_s"] == run.duration_s


def test_timestamps_are_nanoseconds_from_the_start_of_the_window() -> None:
    """The fixture layout declares `capture_ts_ns`; a seconds value would read as 30 ns apart."""
    clock = _FakeTime()
    run = run_capture(
        sources={LEFT: _Source(clock)},
        target_fps=_fps_for(LEFT),
        duration_s=PASSES * PASS_INTERVAL_S,
        clock=clock.read,
    )
    stamps = run.slots[0].capture_ts_ns

    assert all(isinstance(stamp, int) for stamp in stamps)
    assert stamps[-1] > NS_PER_SECOND / TARGET_FPS


def test_the_run_writes_only_what_it_observed(tmp_path) -> None:
    """`descriptors.json` and `expected.json` are the rig's, not the capture's.

    A runner that emitted them would let one capture assert the configuration it was supposed to
    be judged against.
    """
    clock = _FakeTime()
    run = run_capture(
        sources={LEFT: _Source(clock), RIGHT: _Source(clock)},
        target_fps=_fps_for(LEFT, RIGHT),
        duration_s=PASSES * PASS_INTERVAL_S,
        clock=clock.read,
    )

    run.write(tmp_path)

    written = {path.name for path in tmp_path.iterdir()}
    assert written == {CAPTURE_TS_FILENAME, FRAMES_FILENAME}


def test_the_written_documents_carry_the_drop_computers_four_inputs(tmp_path) -> None:
    """`frames.json` must be readable by the hook without anything being derived on the way in."""
    clock = _FakeTime()
    run = run_capture(
        sources={LEFT: _Source(clock)},
        target_fps=_fps_for(LEFT),
        duration_s=PASSES * PASS_INTERVAL_S,
        clock=clock.read,
    )
    run.write(tmp_path)

    frames = json.loads((tmp_path / FRAMES_FILENAME).read_text(encoding="utf-8"))

    assert set(frames[LEFT]) == {"target_fps", "duration_s", "received", "frame_numbers"}
    assert frames[LEFT]["target_fps"] == TARGET_FPS


def test_a_run_with_no_sources_is_refused() -> None:
    """An empty run writes a document that reads as a completed capture with nothing in it."""
    with pytest.raises(CaptureRunError, match="at least one source"):
        run_capture(sources={}, target_fps={}, duration_s=1.0, clock=_FakeTime().read)


def test_a_slot_without_a_declared_rate_is_refused() -> None:
    """A drop rate needs the rate that was asked for; defaulting it invents the denominator."""
    clock = _FakeTime()
    with pytest.raises(CaptureRunError, match="no target_fps declared"):
        run_capture(
            sources={LEFT: _Source(clock), RIGHT: _Source(clock)},
            target_fps=_fps_for(LEFT),
            duration_s=1.0,
            clock=clock.read,
        )


@pytest.mark.parametrize("duration_s", [0.0, -1.0])
def test_a_non_positive_window_is_refused(duration_s: float) -> None:
    """Zero seconds of capture is not a capture, and dividing by it reports the camera."""
    clock = _FakeTime()
    with pytest.raises(CaptureRunError, match="above zero"):
        run_capture(
            sources={LEFT: _Source(clock)},
            target_fps=_fps_for(LEFT),
            duration_s=duration_s,
            clock=clock.read,
        )


def test_slot_order_stability_is_checkable() -> None:
    """The pair spread only describes the cameras while the poll order is fixed."""
    assert slot_order_is_stable([[LEFT, RIGHT], [LEFT, RIGHT]])
    assert not slot_order_is_stable([[LEFT, RIGHT], [RIGHT, LEFT]])
    assert slot_order_is_stable([[LEFT, RIGHT]])


def test_the_window_closes_even_when_no_slot_answers() -> None:
    """Termination is the loop's own property, not something the input guard provides.

    A pass in which every grab returns None must still advance the clock. Without that, the
    window never closes and the run hangs — and a hang that only the argument check prevents is
    one bypassed check away from being reachable.
    """
    clock = _FakeTime()
    run = run_capture(
        sources={LEFT: _Source(clock, drop_on=frozenset(range(1000)))},
        target_fps=_fps_for(LEFT),
        duration_s=PASSES * PASS_INTERVAL_S,
        clock=clock.read,
    )

    assert run.slots[0].received == 0
    assert run.duration_s > 0.0


def test_a_window_cut_short_reports_the_time_it_ran() -> None:
    """A source that stops answering ends the run early, and the record must say so.

    This is the case the acceptance ratio depends on. `compute_drop` divides received frames by
    `target_fps * duration_s`, so a run that recorded the REQUESTED window after stopping early
    counts every unrun second as dropped frames — an operator pressing stop, or a camera that
    went away, reported as a drop rate the rig never had.

    The grabs here cost more than one frame interval each, so the loop crosses the requested
    window part-way through a pass and the elapsed time is strictly greater than the request.
    A run that echoed the request back would report the smaller number.
    """
    clock = _FakeTime(step_s=PASS_INTERVAL_S * 3.0)
    requested = PASSES * PASS_INTERVAL_S

    run = run_capture(
        sources={LEFT: _Source(clock)},
        target_fps=_fps_for(LEFT),
        duration_s=requested,
        clock=clock.read,
    )

    assert run.duration_s > requested
    assert run.duration_s == pytest.approx(run.slots[0].capture_ts_ns[-1] / NS_PER_SECOND)
