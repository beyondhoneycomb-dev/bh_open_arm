"""Open one V4L2 camera and hand `run_capture` the frames it produces.

The calculators, the plans and the refusals all existed before this module and none of them had
ever seen a camera: `controls.py` says so in its own closing line — *"Nothing here opens a camera.
This repository has no camera-opening call path yet."* This is that path, and its whole job is to
reach the same verdicts the pure code already reaches, over a device instead of a fixture.

Every rule below is a measurement on this rig, not an inheritance:

1. **The pixel format is set before the resolution.** These cameras offer YUYV only, and setting
   the resolution first makes the backend try to negotiate MJPEG. The negotiation fails without
   saying so, and what opens is not what was asked for.
2. **The resolution is read back.** A capture opened with no format declared lands at 960×600 on
   the Arducam and 1344×376 on the ZED-M; asked for a size it does not have, V4L2 substitutes the
   nearest one it does and reports success. Every pixel coordinate downstream is then scaled by a
   factor nobody applied, and the frames look correct.
3. **The controls are written after the open, and read back.** An integer control clamps into its
   own bounds and reports success — the Arducam's undeclared floors are `exposure_time_absolute=5`
   and `gain=168`, which is where a rejected write lands. The difference reaches the operator as a
   slightly dark frame and reaches a policy as different training data.
4. **A control the device does not have is skipped.** `-1.0` is the backend's answer for one, and
   the sets genuinely differ: the ZED-M reads `-1.0` for `auto_exposure` and
   `exposure_time_absolute` while still exposing `gain` and `white_balance_temperature`.
5. **The first frames are discarded.** A control write reaches the sensor six frames later —
   frames 0-5 after it still carried the previous exposure. Keeping them measures the setting they
   replaced.
6. **A failure after the open releases the capture.** A node left open makes the next attempt fail
   as "another process holds it", which sends the operator looking for a process that is their own
   previous run.

What this module does not do is decide *which* camera is which. `portpath.node_by_port` already
resolves a bound port to the node on it, and refuses when nothing is there — that is where the
identity lives, because the wrist pair shares one serial and the port is all that separates them.

**Every failure here raises, and that is not a contradiction of tolerant connection.** `02b` §6.2
gives `WP-3B-01` the rule that a dead camera must warn and be skipped rather than fail the arm's
connect — and gives it the path `backend/sensing/connect/**`, describing it as reusing this tree
by import. So the skip is owed one layer up, by the code that opens several cameras and decides
what a rig with one missing can still do. A camera that cannot be opened at the format it was
asked for is a fact this function knows and its caller does not; softening it into a return value
would move the decision to the layer with the least information and leave the tolerant layer
nothing to be tolerant about.

`cv2` is imported inside the call rather than at module scope. It ships in the `robot` extra, and
this tree is imported by callers that do not install it; the enumeration path
(`backend.camera.enumerate_hw`) already treats it as optionally present for the same reason.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from backend.camera.capture_run import GrabbedFrame
from backend.camera.constants import ARDUCAM_PIXEL_FORMAT
from backend.camera.controls import (
    CameraControl,
    assert_controls_locked,
    pixel_format_finding,
    plan_control_writes,
    verify_control_readback,
)
from backend.camera.portpath import CaptureNode

# What a capture backend answers for a property the device does not have. It is a value, not an
# error, so a caller that does not check it writes a control into nothing and verifies it against
# the same nothing.
CONTROL_ABSENT = -1.0

# Frames read and thrown away between configuring the device and offering it to a run. Measured:
# the control write landed on frame 6 (mean 80.47 -> 91.02) with frames 0-5 still carrying the
# previous exposure, and `CAP_PROP_BUFFERSIZE` reads 4 on this device. Ten leaves margin over the
# six that were observed and costs a third of a second against a ten-minute window.
WARMUP_FRAMES = 10

# Milliseconds to nanoseconds. `CAP_PROP_POS_MSEC` carries the V4L2 buffer timestamp, which is on
# `CLOCK_MONOTONIC` — the same base `time.monotonic` reads, verified by bracketing one grab
# between two readings of it.
NS_PER_MS = 1_000_000

# Frames discarded from every camera once they are all open, immediately before the window. Opening
# one camera costs 0.7 s and the ones already open keep streaming into their buffers meanwhile, so
# the first-opened camera starts the run several frames ahead of the last. Deeper than the
# four-deep buffer those frames sat in.
PRERUN_DRAIN_FRAMES = 8

# Frames averaged per brightness reading during identification. Enough to ride over one
# auto-exposure step — which is the failure this averaging exists for, since an exposure
# adjustment between two readings is a brightness change nobody made — and short enough that the
# operator is not holding a hand over a lens for a noticeable time.
PROBE_FRAMES = 5


class V4l2OpenError(RuntimeError):
    """A camera could not be opened in the configuration that was asked for."""


@dataclass(frozen=True)
class CaptureFormat:
    """The stream one camera is opened at.

    Attributes:
        width: Frame width in pixels.
        height: Frame height in pixels.
        fps: Frames per second requested of the device.
        pixel_format: The FOURCC these cameras offer. Uncompressed, which is what makes the
            bandwidth arithmetic exact rather than an estimate.
    """

    width: int
    height: int
    fps: int
    pixel_format: str = ARDUCAM_PIXEL_FORMAT


class CaptureDevice(Protocol):
    """The part of `cv2.VideoCapture` this module uses.

    Spelled in cv2's vocabulary, `isOpened` included, so a real `cv2.VideoCapture` satisfies it
    structurally and no adapter stands between the test and the thing under test.
    """

    def isOpened(self) -> bool:  # noqa: N802 — cv2's spelling, not this project's
        """Whether the device opened."""
        ...

    def set(self, prop: int, value: float) -> bool:  # noqa: A003 — cv2's spelling
        """Write one property."""
        ...

    def get(self, prop: int) -> float:
        """Read one property."""
        ...

    def grab(self) -> bool:
        """Take one frame without decoding it."""
        ...

    def read(self) -> tuple[bool, Any]:
        """Take and decode one frame."""
        ...

    def release(self) -> None:
        """Close the device."""
        ...


class V4l2FrameSource:
    """A `FrameSource` over one configured capture.

    Ownership: owns the capture and closes it. One source per camera, driven by the one thread
    that runs the capture loop — a `cv2.VideoCapture` is not safe to grab from two.

    Attributes:
        label: How this camera is named in a refusal — its port and card.
        skipped_controls: Declared control names this device does not expose.
        pixel_format_finding: The negotiated format when it is not the declared one, else None.
    """

    def __init__(
        self,
        capture: CaptureDevice,
        label: str,
        skipped_controls: tuple[str, ...],
        format_finding: str | None,
    ) -> None:
        """Wrap an already-configured capture.

        Built by `open_frame_source` rather than directly: a capture that reached this
        constructor has had its format verified and its controls locked, and those are the
        properties the frames depend on.

        Args:
            capture: The configured device.
            label: Identifier for messages.
            skipped_controls: Declared names the device does not have.
            format_finding: The pixel-format finding, or None when the format is the declared one.
        """
        self._capture = capture
        self.label = label
        self.skipped_controls = skipped_controls
        self.pixel_format_finding = format_finding

    def grab(self) -> GrabbedFrame | None:
        """Take one frame and report when the driver captured it.

        No frame number travels: `CAP_PROP_POS_FRAMES` reads `-1.0` on every grab of a live
        capture, so this device exposes no counter. A counter of this module's own would be a
        sequence that can never show a gap.

        Returns:
            (GrabbedFrame | None) The frame's capture instant, or None when none arrived.
        """
        import cv2

        if not self._capture.grab():
            return None
        return GrabbedFrame(capture_ts_ns=int(self._capture.get(cv2.CAP_PROP_POS_MSEC) * NS_PER_MS))

    def close(self) -> None:
        """Release the device."""
        self._capture.release()


def drain_stale_frames(
    sources: Sequence[V4l2FrameSource], passes: int = PRERUN_DRAIN_FRAMES
) -> None:
    """Empty every camera's buffer once they are all open, just before the window.

    Cameras open one at a time and each one costs the better part of a second, so the first to
    open is streaming into its buffer while the last is still being configured. Those frames are
    real and their timestamps are honest — the driver captured them, before the run — but the
    camera opened last has no frames from that period at all, so each of them pairs against a
    partner most of a second away. Measured on a six-second two-camera run: `max` 714 ms with
    `q99` 4.8 ms, from exactly four leading frames on the camera opened first.

    Called after opening and before running, not inside either. `open_frame_source` sees one
    camera and cannot know another is still opening, and `run_capture` is driven by synthetic
    sources that have no buffer to empty.

    Args:
        sources: Every source the run will poll.
        passes: Frames to discard from each. Deeper than the buffer they accumulated in.
    """
    for _ in range(passes):
        for source in sources:
            source.grab()


def _control_properties() -> dict[str, int]:
    """Map the V4L2 control names this project declares onto cv2's property ids.

    The two vocabularies are both fixed and neither is derivable from the other, so the crossing
    is written once here. `v4l2-ctl` is absent on this rig, which is what makes cv2 the only
    control path available rather than one of two.

    Returns:
        (dict[str, int]) Control name to cv2 property id.
    """
    import cv2

    return {
        "auto_exposure": cv2.CAP_PROP_AUTO_EXPOSURE,
        "white_balance_automatic": cv2.CAP_PROP_AUTO_WB,
        "exposure_time_absolute": cv2.CAP_PROP_EXPOSURE,
        "gain": cv2.CAP_PROP_GAIN,
        "white_balance_temperature": cv2.CAP_PROP_WB_TEMPERATURE,
    }


def _present_controls(
    capture: CaptureDevice, declared: Sequence[CameraControl], properties: Mapping[str, int]
) -> dict[str, int]:
    """Read the declared controls this device actually has, and their current values.

    Membership is what `plan_control_writes` reads as "the device has this control", so a name
    answering `CONTROL_ABSENT` is left out rather than recorded as a value.

    Args:
        capture: The open device.
        declared: The controls this camera is declared to hold.
        properties: Control name to cv2 property id.

    Returns:
        (dict[str, int]) Control name to current value, for the ones the device exposes.
    """
    present: dict[str, int] = {}
    for control in declared:
        prop = properties.get(control.name)
        if prop is None:
            continue
        value = capture.get(prop)
        if value == CONTROL_ABSENT:
            continue
        present[control.name] = int(value)
    return present


def _default_open(device: str) -> CaptureDevice:
    """Open a device through cv2's V4L2 backend.

    The backend is named rather than left to cv2's search order: the search picks whichever
    backend answers first, and only V4L2 carries the controls and the buffer timestamp this
    module reads.

    Args:
        device: The device node path.

    Returns:
        (CaptureDevice) The opened capture, which may not have opened.
    """
    import cv2

    return cv2.VideoCapture(device, cv2.CAP_V4L2)


def open_frame_source(
    node: CaptureNode,
    capture_format: CaptureFormat,
    declared_controls: Sequence[CameraControl],
    open_capture: Callable[[str], CaptureDevice] | None = None,
    warmup_frames: int = WARMUP_FRAMES,
) -> V4l2FrameSource:
    """Open one camera at the declared format with the declared controls, or refuse.

    The order is the contract, and each step is verified rather than trusted: format, then
    resolution readback, then controls, then their readback, then the warm-up. Anything that
    fails after the device opened releases it on the way out.

    Args:
        node: The capture node to open, already resolved from its bound port.
        capture_format: The stream to open at.
        declared_controls: The controls this camera is declared to hold.
        open_capture: How to open the device, injected so the ordering rules and every refusal
            are driven without hardware. None uses cv2's V4L2 backend.
        warmup_frames: Frames to read and discard after configuring.

    Returns:
        (V4l2FrameSource) The configured source.

    Raises:
        V4l2OpenError: If the device does not open, or opens at a resolution other than the one
            asked for.
        CameraControlError: If a declared control does not read back at its declared value, or
            if the device reports no controls at all.
    """
    import cv2

    opener = open_capture if open_capture is not None else _default_open
    device = str(node.device)
    label = f"{node.card} on {node.port_path} ({device})"

    capture = opener(device)
    if not capture.isOpened():
        raise V4l2OpenError(
            f"{label} did not open. The usual cause is another process still holding the node — "
            f"a previous run, or a viewer left running. `ls -l /proc/*/fd/* | grep {device}` "
            "names it"
        )
    try:
        _configure(capture, capture_format, label, cv2)
        skipped, finding = _lock_controls(capture, declared_controls, capture_format, label, cv2)
        for _ in range(warmup_frames):
            capture.read()
    except BaseException:
        # Released on every failure path, including a cancellation. What this costs to skip is
        # not this run — it is the next one, which fails as "another process holds it" and sends
        # the operator after a process that is their own.
        capture.release()
        raise
    return V4l2FrameSource(
        capture=capture, label=label, skipped_controls=skipped, format_finding=finding
    )


def _configure(capture: CaptureDevice, capture_format: CaptureFormat, label: str, cv2: Any) -> None:
    """Set the format and prove the device took the resolution.

    Args:
        capture: The open device.
        capture_format: The stream to open at.
        label: Identifier for the refusal.
        cv2: The imported module, passed so the deferred import happens once per open.

    Raises:
        V4l2OpenError: If the device is running a resolution other than the one asked for.
    """
    # FOURCC first. With the resolution set first the backend negotiates a format these cameras
    # do not offer, and the failure is silent.
    capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*capture_format.pixel_format))
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, capture_format.width)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, capture_format.height)
    capture.set(cv2.CAP_PROP_FPS, capture_format.fps)

    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if (width, height) != (capture_format.width, capture_format.height):
        raise V4l2OpenError(
            f"{label} is running {width}x{height}, not the requested "
            f"{capture_format.width}x{capture_format.height}. V4L2 substituted the nearest size "
            "it has and reported success — every pixel coordinate downstream would be scaled by "
            "a factor nothing applied. `v4l2-ctl -d <device> --list-formats-ext` lists what it "
            "does have"
        )


def _lock_controls(
    capture: CaptureDevice,
    declared: Sequence[CameraControl],
    capture_format: CaptureFormat,
    label: str,
    cv2: Any,
) -> tuple[tuple[str, ...], str | None]:
    """Write the declared controls in a safe order and prove each one took.

    Args:
        capture: The open, formatted device.
        declared: The controls this camera is declared to hold.
        capture_format: The stream, for the pixel-format finding.
        label: Identifier for the refusal.
        cv2: The imported module.

    Returns:
        (tuple) The declared names this device does not expose, and the pixel-format finding.

    Raises:
        CameraControlError: If a control did not read back at its declared value.
    """
    format_finding = pixel_format_finding(
        capture_format.pixel_format, int(capture.get(cv2.CAP_PROP_FOURCC))
    )
    if not declared:
        # Declaring nothing and reading nothing are different events, and only the second is a
        # fault. `plan_control_writes` refuses an empty readback because a UVC camera exposes
        # controls, so an empty answer means the read failed — but that reasoning never reaches a
        # camera this project has written no values for. The ZED-M is one: its ranges are
        # unmeasured here and `v4l2-ctl`, which is how a range is read, is not on this rig.
        # Opening it at its defaults is what can be claimed honestly; refusing it would refuse a
        # camera over a declaration nobody wrote.
        return (), format_finding

    properties = _control_properties()
    unmapped = sorted({c.name for c in declared} - set(properties))
    if unmapped:
        # This module's gap, not the device's. Left to fall through it empties the readback and
        # earns the "no controls at all" refusal, which is a true sentence about a false cause —
        # it sends the operator to `v4l2-ctl` and a camera that is working correctly.
        raise V4l2OpenError(
            f"{label}: {', '.join(unmapped)} is declared for this camera but this module has no "
            "cv2 property to write it through. The V4L2 names and cv2's property ids are two "
            "fixed vocabularies and the crossing between them lives in `_control_properties`; "
            "add the pair there rather than dropping the control"
        )
    plan = plan_control_writes(declared, _present_controls(capture, declared, properties))
    for control in plan.ordered:
        capture.set(properties[control.name], control.value)

    after = {control.name: int(capture.get(properties[control.name])) for control in plan.ordered}
    assert_controls_locked(verify_control_readback(plan, after), label)

    return plan.skipped, format_finding


class BrightnessProbe:
    """Opens a node just far enough to answer "how bright is this view right now?".

    Ownership: owns the capture and closes it. Used by the bind flow, never by a run.

    It deliberately does NOT go through `open_frame_source`. That path forces a declared format
    and verifies declared controls, and both are properties of the SLOT — which is the thing bind
    is trying to work out. A camera that will not take 1920x1200 must still be identifiable, or
    the operator is told to fix a binding they cannot record.

    Frames are averaged rather than sampled once: a single frame catches the auto-exposure
    mid-adjust, and an exposure step reads as a covered lens.
    """

    def __init__(self, capture: CaptureDevice, frames: int) -> None:
        """Wrap an open capture.

        Args:
            capture: The open device.
            frames: Frames to average per reading.
        """
        self._capture = capture
        self._frames = frames

    def __call__(self) -> float:
        """Return the mean brightness of the next frames, normalised to 0..1.

        Returns:
            (float) Mean sample value over the device's full range, or 0.0 when no frame
                arrived — which the caller reads as a black baseline and refuses on, rather than
                as a camera that happens to be dark.
        """
        import numpy

        means: list[float] = []
        for _ in range(self._frames):
            ok, frame = self._capture.read()
            if not ok or frame is None:
                continue
            array = numpy.asarray(frame)
            # The device's own full scale, not a hardcoded 255: a 10-bit camera surfaced as
            # uint16 would otherwise read four times too bright and never clear any threshold.
            full_scale = (
                float(numpy.iinfo(array.dtype).max)
                if numpy.issubdtype(array.dtype, numpy.integer)
                else 1.0
            )
            means.append(float(array.mean()) / full_scale)
        if not means:
            return 0.0
        return sum(means) / len(means)

    def close(self) -> None:
        """Release the device."""
        self._capture.release()


def open_brightness_probe(
    node: CaptureNode,
    frames: int = PROBE_FRAMES,
    open_capture: Callable[[str], CaptureDevice] | None = None,
) -> BrightnessProbe:
    """Open a node at whatever format it defaults to, for identification only.

    Args:
        node: The capture node to open.
        frames: Frames to average per reading.
        open_capture: How to open the device, injected so the bind flow is drivable with no
            camera. None uses cv2's V4L2 backend.

    Returns:
        (BrightnessProbe) The probe, which owns the device until closed.

    Raises:
        V4l2OpenError: If the device does not open.
    """
    opener = _default_open if open_capture is None else open_capture
    capture = opener(str(node.device))
    if not capture.isOpened():
        capture.release()
        raise V4l2OpenError(f"{node.card} at {node.port_path} ({node.device}) did not open")
    return BrightnessProbe(capture, frames)


__all__ = [
    "CONTROL_ABSENT",
    "NS_PER_MS",
    "PRERUN_DRAIN_FRAMES",
    "PROBE_FRAMES",
    "WARMUP_FRAMES",
    "BrightnessProbe",
    "CaptureDevice",
    "CaptureFormat",
    "V4l2FrameSource",
    "V4l2OpenError",
    "drain_stale_frames",
    "open_brightness_probe",
    "open_frame_source",
]
