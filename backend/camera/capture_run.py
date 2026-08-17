"""Grab from several cameras for a fixed window and write what `reverify` already judges.

This is the missing half of WP-3C-01. Every calculator the gate needs exists —
`backend.camera.droprate` counts what did not arrive, `backend.camera.syncslop` pairs the
timestamps and reports `q99_ms`, `backend.camera.bandwidth` sums the profiles — and none of them
has ever been handed real bytes, because nothing in the tree opens a camera and records what it
saw. This does that and stops there: it produces the fixture layout
`backend.camera.reverify.reverify_from_fixture` already reads, so the run and the verdict stay
separate and the verdict is reached by the same code a synthetic fixture reaches it by.

**One capture answers two acceptance items.** `PG-CAM-001` ③ wants the pair timestamp spread and
④ wants the per-slot drop rate over ten continuous minutes; both are computed from one list of
`capture_ts` per slot, so a second run would only be a second chance to disagree with the first.

Three properties of these cameras are not this module's to discover, and getting any of them
wrong makes the numbers meaningless rather than wrong-looking. They are inherited from the
sibling rig, which measured them on the same Arducam B0495 model:

1. **FOURCC is set before the resolution.** Setting the resolution first makes OpenCV try to
   negotiate MJPEG, which these cameras do not offer; the failure is silent and what opens is
   not the format that was asked for. YUYV is the only format they have.
2. **The controls are written after the open, not left at their defaults.** An Arducam opens at
   `exposure_time_absolute=660` and `gain=1600` — both at maximum — and every frame comes back
   clipped to white. A drop rate measured through that is real, and the footage behind it is
   unusable.
3. **The `card` name is compared after resolving `by-path`.** The two wrist cameras share a
   serial, so `by-id` names only one of them and the port path is the only stable identifier.
   Moving a plug does not break the symlink — it silently points at the other camera, which is
   left and right swapped with nothing failing.

The bandwidth half of acceptance ② is not computed here. `backend.camera.bandwidth` already sums
profiles and per-controller shares from the enumerated descriptors, and uncompressed YUYV makes
that arithmetic exact rather than an estimate — a second implementation over the same numbers
could only disagree with it.
"""

from __future__ import annotations

import json
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from backend.camera.reverify import (
    CAPTURE_TS_FILENAME,
    FRAMES_FILENAME,
)

# Nanoseconds per second, for stamping `capture_ts` in the unit the fixture layout declares.
NS_PER_SECOND = 1_000_000_000

# The window `PG-CAM-001` ④ asks for. Ten continuous minutes, because a drop that only appears
# after the buffers have been cycling for minutes is exactly the one a short run reports as
# healthy.
ACCEPTANCE_DURATION_S = 600.0

# How long a single grab may block before the run calls the slot silent for that attempt. One
# frame interval at 30 fps is 33 ms; this is several of those, so a late frame is late rather
# than missing, and a camera that has actually stopped is not waited on for a whole second.
GRAB_TIMEOUT_S = 0.2


@dataclass(frozen=True)
class GrabbedFrame:
    """One frame that arrived, and whatever its device could say about it.

    Both fields are optional because a real device supplies neither by default and the two
    absences mean different things. Folding either into a sentinel on the return channel is what
    the old `int | None` did, and it made "a frame arrived without a number" unsayable — so the
    only source that could satisfy the Protocol was one that invented a counter.

    Attributes:
        frame_number: The device's own frame counter, or None when it exposes none. A
            `cv2.VideoCapture` over V4L2 exposes none: `CAP_PROP_POS_FRAMES` reads `-1.0` on
            every grab of a live capture. A counter synthesised here would be a sequence that
            can never show a gap, which is a device that cannot drop.
        capture_ts_ns: The instant the device captured the frame, absolute monotonic
            nanoseconds, or None when it does not stamp. V4L2 stamps every buffer on
            `CLOCK_MONOTONIC` and `cv2` surfaces it as `CAP_PROP_POS_MSEC`.
    """

    frame_number: int | None = None
    capture_ts_ns: int | None = None


class FrameSource(Protocol):
    """The one capability this run needs from a camera, and nothing wider.

    Structural so a synthetic source satisfies it exactly as a `cv2.VideoCapture` wrapper does.
    A run driven by a double therefore exercises the same loop, the same timestamping and the
    same accounting as a run driven by hardware — only the bytes differ.
    """

    def grab(self) -> GrabbedFrame | None:
        """Take one frame, or answer None when none arrived.

        None is absence and nothing else: it is what `compute_drop` reads as a drop. A frame
        that arrived says so by being a `GrabbedFrame`, whether or not its device could number
        or stamp it.
        """
        ...


@dataclass(frozen=True)
class SlotCapture:
    """What one slot produced during the window.

    Attributes:
        slot: The slot key, matching the camera registry's naming.
        target_fps: The rate the profile asked the camera for.
        capture_ts_ns: One timestamp per frame that arrived, host monotonic nanoseconds.
        frame_numbers: The device frame numbers that arrived, where the device exposes them.
    """

    slot: str
    target_fps: float
    capture_ts_ns: tuple[int, ...]
    frame_numbers: tuple[int, ...]

    @property
    def received(self) -> int:
        """How many frames arrived."""
        return len(self.capture_ts_ns)


@dataclass(frozen=True)
class CaptureRun:
    """One window's capture across every slot.

    Attributes:
        duration_s: The window the run actually covered, measured rather than assumed. A run cut
            short by an operator still produces a usable drop rate against the time it did run,
            and using the requested duration instead would report those unrun seconds as drops.
        slots: What each slot produced.
    """

    duration_s: float
    slots: tuple[SlotCapture, ...]

    def capture_ts_document(self) -> dict[str, list[int]]:
        """The `capture_ts.json` body: slot to its timestamp list."""
        return {slot.slot: list(slot.capture_ts_ns) for slot in self.slots}

    def frames_document(self) -> dict[str, dict[str, Any]]:
        """The `frames.json` body: slot to the drop computer's four inputs."""
        return {
            slot.slot: {
                "target_fps": slot.target_fps,
                "duration_s": self.duration_s,
                "received": slot.received,
                "frame_numbers": list(slot.frame_numbers),
            }
            for slot in self.slots
        }

    def write(self, directory: Path) -> None:
        """Write the two fixture files this run produces.

        `descriptors.json` and `expected.json` are deliberately not written here. They describe
        what the rig IS — which cameras are registered and what the link may carry — rather than
        what this window observed, and a runner that emitted them would let a capture assert the
        configuration it was supposed to be judged against.

        Args:
            directory: The fixture directory; created if absent.
        """
        directory.mkdir(parents=True, exist_ok=True)
        (directory / CAPTURE_TS_FILENAME).write_text(
            json.dumps(self.capture_ts_document(), indent=2), encoding="utf-8"
        )
        (directory / FRAMES_FILENAME).write_text(
            json.dumps(self.frames_document(), indent=2), encoding="utf-8"
        )


class CaptureRunError(RuntimeError):
    """Raised when a run cannot produce numbers a verdict may be reached on."""


def run_capture(
    sources: Mapping[str, FrameSource],
    target_fps: Mapping[str, float],
    duration_s: float,
    clock: Any = time.perf_counter,
) -> CaptureRun:
    """Grab from every slot for `duration_s` and record when each frame arrived.

    Every slot is polled once per pass in a fixed order, so the pass rate is the slowest camera's
    and the timestamp spread between two slots is what the pair actually achieved rather than an
    artefact of one being read first every time. Ordering the slots differently per pass would
    average that spread away, and the spread is the measurement.

    A grab that returns nothing is recorded by omission: no timestamp is appended, so the frame
    is missing from both the count and the sequence, which is what `compute_drop` reads as a
    drop. Nothing is substituted, because a synthesised timestamp would make the slop
    distribution describe this function instead of the cameras.

    Args:
        sources: Slot key to its frame source. At least one.
        target_fps: Slot key to the rate its profile requested. Must cover every slot.
        duration_s: How long to capture, seconds; must be above zero.
        clock: Monotonic seconds source, injected so a test can drive a window without waiting.

    Returns:
        (CaptureRun) What every slot produced, and the window actually covered.

    Raises:
        CaptureRunError: When no sources are given, when a slot has no declared rate, or when
            the duration is not above zero. Each would otherwise produce a document that reads
            as a completed capture with nothing in it.
    """
    if not sources:
        raise CaptureRunError("a capture needs at least one source")
    if duration_s <= 0.0:
        raise CaptureRunError(f"duration_s must be above zero, got {duration_s}")
    missing = sorted(set(sources) - set(target_fps))
    if missing:
        raise CaptureRunError(
            f"no target_fps declared for {missing}; a drop rate needs the rate that was asked "
            "for, and defaulting it would report the camera against a number nobody chose"
        )

    order = tuple(sources)
    stamps: dict[str, list[int]] = {slot: [] for slot in order}
    numbers: dict[str, list[int]] = {slot: [] for slot in order}
    device_clocked: bool | None = None
    started = clock()
    now = started
    while now - started < duration_s:
        for slot in order:
            # Stamped immediately after this slot's grab returns and BEFORE the next slot is
            # polled, so a host-stamped run records when the frame arrived rather than when the
            # pass finished. Reading the clock once per pass and reusing it would give every
            # slot in the pass the same timestamp — and the difference between two slots in one
            # pass is exactly what the sync-slop report measures, so that shortcut reports a
            # perfectly synchronised rig whatever the cameras did.
            grabbed = sources[slot].grab()
            now = clock()
            if grabbed is None:
                continue
            device_clocked = _one_time_base(device_clocked, grabbed, slot)
            stamps[slot].append(
                grabbed.capture_ts_ns
                if grabbed.capture_ts_ns is not None
                else int((now - started) * NS_PER_SECOND)
            )
            if grabbed.frame_number is not None:
                numbers[slot].append(grabbed.frame_number)
        # Advanced once per pass as well as per slot, so the loop's exit does not depend on any
        # slot having been polled. Without it a pass that polls nothing never moves `now`, and
        # the window never closes — a termination that rests on an input guard rather than on
        # the loop's own structure is one bypassed guard away from a hang.
        now = clock()
    elapsed = now - started

    if device_clocked:
        stamps = _rebased_to_run_start(stamps)

    return CaptureRun(
        duration_s=elapsed,
        slots=tuple(
            SlotCapture(
                slot=slot,
                target_fps=target_fps[slot],
                capture_ts_ns=tuple(stamps[slot]),
                frame_numbers=tuple(numbers[slot]),
            )
            for slot in order
        ),
    )


def _one_time_base(device_clocked: bool | None, grabbed: GrabbedFrame, slot: str) -> bool:
    """Return whether this run is device-clocked, refusing the first frame that disagrees.

    A document holding some slots on the driver's clock and others on this host's is one whose
    between-slot differences are arithmetic across two unrelated origins. The number it yields is
    shaped exactly like a sync slop and describes nothing, so it is refused rather than reported —
    and refused on the frame that reveals it, because the run it would otherwise spoil is ten
    minutes long.

    Args:
        device_clocked: What earlier frames established, or None before any arrived.
        grabbed: The frame that just arrived.
        slot: The slot it arrived on, named in the refusal.

    Returns:
        (bool) True when this run's timestamps come from the devices.

    Raises:
        CaptureRunError: When this frame's time base is not the one the run already has.
    """
    stamped = grabbed.capture_ts_ns is not None
    if device_clocked is None or device_clocked == stamped:
        return stamped
    raise CaptureRunError(
        f"{slot!r} answered on a different time base from the slots before it: this run is "
        f"{'device' if device_clocked else 'host'}-clocked and that frame is "
        f"{'device' if stamped else 'host'}-clocked. A capture must keep one clock, or the "
        "spread between two slots is a subtraction across two origins"
    )


def _rebased_to_run_start(stamps: Mapping[str, list[int]]) -> dict[str, list[int]]:
    """Shift device timestamps to start near zero, keeping the offsets between slots.

    One base for the whole run, never one per slot. The offset between two cameras' capture
    instants is the thing `PG-CAM-001` ③ measures; subtracting each slot's own first stamp sets
    every slot's first frame to zero and reports a pair that is perfectly in phase, whatever the
    cameras did.

    Args:
        stamps: Per-slot absolute device timestamps in nanoseconds.

    Returns:
        (dict[str, list[int]]) The same timestamps relative to the run's earliest frame.
    """
    arrivals = [slot_stamps[0] for slot_stamps in stamps.values() if slot_stamps]
    if not arrivals:
        return {slot: list(slot_stamps) for slot, slot_stamps in stamps.items()}
    base = min(arrivals)
    return {slot: [stamp - base for stamp in slot_stamps] for slot, slot_stamps in stamps.items()}


def slot_order_is_stable(passes: Sequence[Sequence[str]]) -> bool:
    """Whether every pass polled the slots in the same order.

    Exposed so a run can assert its own precondition rather than assume it: the pair timestamp
    spread only describes the cameras while the order is fixed, and a run that rotated it would
    produce a smaller spread that nothing downstream could tell from a better-synchronised rig.

    Args:
        passes: The slot order used on each pass.

    Returns:
        (bool) True when fewer than two passes were made, or all passes agree.
    """
    if len(passes) < 2:
        return True
    first = tuple(passes[0])
    return all(tuple(order) == first for order in passes[1:])
