"""Opening a real camera: the order, the readbacks, and what each failure costs.

No camera is opened here. The capture is injected, so every ordering rule and every refusal is
driven without hardware — which is the only way they can be tested at all, because each of them
exists to stop a silent success and a silent success looks identical to a working camera.

Every number and every rule below was measured on this rig rather than inherited:

- A `cv2.VideoCapture` opened with no format lands at 960×600 on the Arducam and 1344×376 on the
  ZED-M, not at what the profile asks for. V4L2 substitutes silently, so the readback is the only
  thing that separates "the camera is running the profile" from "the camera is running something".
- `-1.0` is how the backend answers for a control the device does not have: the ZED-M reads that
  for `auto_exposure` and `exposure_time_absolute`, while still exposing `gain` and
  `white_balance_temperature`. A device's control set is therefore discovered, never assumed.
- A control write reaches the sensor six frames later. Frames 0-5 after the write still carried
  the previous exposure and only frame 6 showed the new one, so the frames a run keeps have to
  start after that.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.camera.capture_run import GrabbedFrame
from backend.camera.constants import ARDUCAM_PIXEL_FORMAT
from backend.camera.controls import CameraControl, CameraControlError
from backend.camera.portpath import CaptureNode
from backend.camera.v4l2_source import (
    CONTROL_ABSENT,
    PRERUN_DRAIN_FRAMES,
    WARMUP_FRAMES,
    CaptureFormat,
    V4l2OpenError,
    drain_stale_frames,
    open_frame_source,
)

CARD = "Arducam B0495 (USB3 2.3MP)"
PORT = "usb-0000:00:0d.0-1.1.1"
DEVICE = "/dev/video0"

FORMAT = CaptureFormat(width=1920, height=1200, fps=30, pixel_format=ARDUCAM_PIXEL_FORMAT)

# What the device lands on when nothing declares a format — measured on this Arducam.
UNDECLARED_WIDTH = 960
UNDECLARED_HEIGHT = 600

DECLARED = (
    CameraControl("auto_exposure", 1),
    CameraControl("white_balance_automatic", 0),
    CameraControl("exposure_time_absolute", 60),
    CameraControl("gain", 200),
)

# The driver's capture instant for the first frame, absolute monotonic nanoseconds.
FIRST_STAMP_MS = 596_133_450.753

# The cv2 property each declared control is written through, resolved late because cv2 is an
# optional extra and this module must import without it.
_PROPERTY_FOR = {
    "auto_exposure": lambda cv2: cv2.CAP_PROP_AUTO_EXPOSURE,
    "white_balance_automatic": lambda cv2: cv2.CAP_PROP_AUTO_WB,
    "exposure_time_absolute": lambda cv2: cv2.CAP_PROP_EXPOSURE,
    "gain": lambda cv2: cv2.CAP_PROP_GAIN,
}


def _node() -> CaptureNode:
    return CaptureNode(device=Path(DEVICE), card=CARD, port_path=PORT)


class FakeCapture:
    """A `cv2.VideoCapture` double that records the order it was configured in.

    It answers property reads out of a dict the test seeds, so a device that substitutes a
    resolution, refuses a control or lacks one entirely is expressed by seeding that dict rather
    than by a flag this class interprets.
    """

    def __init__(
        self,
        properties: dict[int, float],
        opened: bool = True,
        clamp: dict[int, float] | None = None,
    ) -> None:
        self.properties = properties
        self._opened = opened
        self._clamp = clamp or {}
        self.set_order: list[int] = []
        self.grab_answers = True
        self.grabs = 0
        self.reads = 0
        self.released = False

    # The two names below are cv2's, not this project's. A double that renamed them would no
    # longer satisfy the Protocol a `cv2.VideoCapture` satisfies, which is the whole reason the
    # Protocol is spelled in cv2's vocabulary — so the naming rules are suppressed at the two
    # lines a third-party API dictates, and nowhere else.
    def isOpened(self) -> bool:  # noqa: N802
        """Whether the device opened."""
        return self._opened

    def set(self, prop: int, value: float) -> bool:  # noqa: A003
        """Record the write in order, landing on the clamped value where one is seeded."""
        self.set_order.append(prop)
        self.properties[prop] = self._clamp.get(prop, value)
        return True

    def get(self, prop: int) -> float:
        """Answer the current property, or the absent sentinel when it was never seeded."""
        return float(self.properties.get(prop, CONTROL_ABSENT))

    def grab(self) -> bool:
        """Take one frame, or report that nothing arrived."""
        self.grabs += 1
        return self.grab_answers

    def read(self) -> tuple[bool, object]:
        """Take and decode one frame; only the warm-up uses this."""
        self.reads += 1
        return True, object()

    def release(self) -> None:
        """Close the device."""
        self.released = True


def _cv2():
    """The cv2 module, skipping the test when the robot extra is not installed."""
    return pytest.importorskip("cv2")


def _seeded(cv2, **overrides: float) -> dict[int, float]:
    """A property dict for a healthy Arducam at the declared format."""
    seeded = {
        cv2.CAP_PROP_FRAME_WIDTH: float(FORMAT.width),
        cv2.CAP_PROP_FRAME_HEIGHT: float(FORMAT.height),
        cv2.CAP_PROP_FPS: float(FORMAT.fps),
        cv2.CAP_PROP_FOURCC: float(cv2.VideoWriter_fourcc(*ARDUCAM_PIXEL_FORMAT)),
        cv2.CAP_PROP_POS_MSEC: FIRST_STAMP_MS,
        cv2.CAP_PROP_AUTO_EXPOSURE: 0.0,
        cv2.CAP_PROP_AUTO_WB: 1.0,
        cv2.CAP_PROP_EXPOSURE: 5.0,
        cv2.CAP_PROP_GAIN: 168.0,
    }
    seeded.update(overrides)
    return seeded


def _open(capture: FakeCapture, controls=DECLARED):
    """Open a source over the given capture double."""
    return open_frame_source(
        node=_node(),
        capture_format=FORMAT,
        declared_controls=controls,
        open_capture=lambda _device: capture,
    )


def test_the_pixel_format_is_set_before_the_resolution() -> None:
    """Setting the resolution first makes the backend negotiate a format these cameras lack.

    The failure is silent — what opens is not what was asked for — so the order is asserted
    rather than left to whichever line someone writes first.
    """
    cv2 = _cv2()
    capture = FakeCapture(_seeded(cv2))

    _open(capture).close()

    written = capture.set_order
    assert written.index(cv2.CAP_PROP_FOURCC) < written.index(cv2.CAP_PROP_FRAME_WIDTH)
    assert written.index(cv2.CAP_PROP_FOURCC) < written.index(cv2.CAP_PROP_FRAME_HEIGHT)


def test_a_substituted_resolution_is_refused() -> None:
    """V4L2 answers a size it does not have with the nearest one it does, and reports success.

    Every pixel coordinate downstream is then off by a scale nobody applied, and the frames look
    fine.
    """
    cv2 = _cv2()
    capture = FakeCapture(
        _seeded(cv2),
        clamp={
            cv2.CAP_PROP_FRAME_WIDTH: float(UNDECLARED_WIDTH),
            cv2.CAP_PROP_FRAME_HEIGHT: float(UNDECLARED_HEIGHT),
        },
    )

    with pytest.raises(V4l2OpenError, match=f"{UNDECLARED_WIDTH}x{UNDECLARED_HEIGHT}"):
        _open(capture)

    assert capture.released


def test_the_controls_are_written_after_the_device_is_open() -> None:
    """A control written before the open is written to a device that is not streaming yet.

    Ordering it after the format also means the writes land on the stream the run will use.
    """
    cv2 = _cv2()
    capture = FakeCapture(_seeded(cv2))

    _open(capture).close()

    written = capture.set_order
    assert written.index(cv2.CAP_PROP_FRAME_WIDTH) < written.index(cv2.CAP_PROP_AUTO_EXPOSURE)
    assert capture.properties[cv2.CAP_PROP_EXPOSURE] == 60.0
    assert capture.properties[cv2.CAP_PROP_GAIN] == 200.0


def test_the_automatic_switches_are_written_before_what_they_guard() -> None:
    """`exposure_time_absolute` is inactive while auto exposure owns it, and the write is lost."""
    cv2 = _cv2()
    capture = FakeCapture(_seeded(cv2))

    _open(capture).close()

    written = capture.set_order
    assert written.index(cv2.CAP_PROP_AUTO_EXPOSURE) < written.index(cv2.CAP_PROP_EXPOSURE)
    assert written.index(cv2.CAP_PROP_AUTO_WB) < written.index(cv2.CAP_PROP_EXPOSURE)


def test_a_control_the_device_does_not_have_is_skipped_rather_than_written() -> None:
    """The ZED-M answers `-1.0` for the exposure controls while still exposing others.

    Writing one anyway would be a write nothing can verify, and refusing the camera over it
    would refuse a camera that is working exactly as its class allows.
    """
    cv2 = _cv2()
    properties = _seeded(cv2)
    del properties[cv2.CAP_PROP_EXPOSURE]
    capture = FakeCapture(properties)

    source = _open(capture)
    source.close()

    assert "exposure_time_absolute" in source.skipped_controls
    assert cv2.CAP_PROP_EXPOSURE not in capture.set_order


def test_a_control_that_read_back_wrong_refuses_and_releases() -> None:
    """An integer control clamps into its own bounds and reports the write succeeded.

    Releasing on the way out is half the fix: a capture left open makes the next attempt fail as
    "another process holds it", which sends the operator after the wrong thing.
    """
    cv2 = _cv2()
    capture = FakeCapture(_seeded(cv2), clamp={cv2.CAP_PROP_GAIN: 1600.0})

    with pytest.raises(CameraControlError, match="gain"):
        _open(capture)

    assert capture.released


def test_a_device_that_will_not_open_is_refused_by_name() -> None:
    """The commonest cause is another process still holding the node, so the message says so."""
    cv2 = _cv2()
    capture = FakeCapture(_seeded(cv2), opened=False)

    with pytest.raises(V4l2OpenError, match=DEVICE):
        _open(capture)


def test_the_first_frames_are_discarded_before_any_are_offered() -> None:
    """Measured: a control write reaches the sensor six frames later.

    A run that kept those frames would measure the exposure it replaced, and the drop rate would
    be computed over frames the operator never configured.
    """
    cv2 = _cv2()
    capture = FakeCapture(_seeded(cv2))

    _open(capture).close()

    assert capture.reads == WARMUP_FRAMES
    assert WARMUP_FRAMES > 6


def test_a_grab_reports_the_driver_capture_instant_and_no_frame_number() -> None:
    """`CAP_PROP_POS_MSEC` is the V4L2 buffer timestamp; `CAP_PROP_POS_FRAMES` reads -1.0."""
    cv2 = _cv2()
    capture = FakeCapture(_seeded(cv2))
    source = _open(capture)

    grabbed = source.grab()
    source.close()

    assert grabbed == GrabbedFrame(frame_number=None, capture_ts_ns=int(FIRST_STAMP_MS * 1e6))


def test_a_grab_that_took_nothing_reports_absence() -> None:
    """The absence is the drop, and it must not arrive as a frame with a stale timestamp."""
    cv2 = _cv2()
    capture = FakeCapture(_seeded(cv2))
    source = _open(capture)
    capture.grab_answers = False

    assert source.grab() is None
    source.close()


def test_a_negotiated_format_that_differs_is_reported_and_not_refused() -> None:
    """`06` FR-CAM-071 fixes this direction: the driver picks what it can deliver.

    It still has to reach someone, because the bandwidth budget was computed from the declared
    format's bytes per pixel.
    """
    cv2 = _cv2()
    capture = FakeCapture(
        _seeded(cv2), clamp={cv2.CAP_PROP_FOURCC: float(cv2.VideoWriter_fourcc(*"MJPG"))}
    )

    source = _open(capture)
    source.close()

    assert source.pixel_format_finding is not None
    assert "MJPG" in source.pixel_format_finding


def test_draining_discards_the_frames_buffered_before_the_run() -> None:
    """Cameras are opened one at a time, so the first one streams while the next is still opening.

    Measured: opening one camera costs 0.7 s, and the one already open filled its four-deep
    buffer meanwhile. Those frames are real and their timestamps are honest — they were captured
    before the window — but the camera opened last has none of them, so every one of them pairs
    against a partner most of a second away. On a six-second run that put `max` at 714 ms with
    `q99` at 4.8; the frames are dropped rather than the outlier explained away, because a run
    that begins with one camera ahead of another has not begun.
    """
    cv2 = _cv2()
    first = FakeCapture(_seeded(cv2))
    second = FakeCapture(_seeded(cv2))
    sources = [_open(first), _open(second)]
    grabs_after_open = (first.grabs, second.grabs)

    drain_stale_frames(sources)

    assert first.grabs - grabs_after_open[0] == PRERUN_DRAIN_FRAMES
    assert second.grabs - grabs_after_open[1] == PRERUN_DRAIN_FRAMES


def test_the_drain_is_deeper_than_the_buffer_it_empties() -> None:
    """`CAP_PROP_BUFFERSIZE` reads 4 on these cameras and four stale frames were observed."""
    assert PRERUN_DRAIN_FRAMES > 4


def test_a_camera_with_nothing_declared_is_opened_without_controls() -> None:
    """Declaring nothing and reading nothing are different events with one honest answer each.

    `plan_control_writes` refuses an empty readback because a UVC camera exposes controls and an
    empty answer means the read failed. That reasoning does not reach a camera for which this
    project has declared no values — the ZED-M's ranges are unmeasured here and `v4l2-ctl`, which
    is how a range is read, is not installed on this rig. Opening it at its defaults is what this
    project can honestly claim; refusing it would refuse a camera over a declaration nobody wrote.
    """
    cv2 = _cv2()
    capture = FakeCapture(_seeded(cv2))

    source = _open(capture, controls=())
    source.close()

    assert source.skipped_controls == ()
    assert cv2.CAP_PROP_GAIN not in capture.set_order


def test_a_declared_control_against_an_empty_readback_is_still_refused() -> None:
    """The guard that the case above steps around must still catch the case it was written for."""
    cv2 = _cv2()
    properties = _seeded(cv2)
    for control in DECLARED:
        properties.pop(_PROPERTY_FOR[control.name](cv2), None)
    capture = FakeCapture(properties)

    with pytest.raises(CameraControlError, match="no controls at all"):
        _open(capture)


def test_a_declared_control_this_module_cannot_write_is_named_as_such() -> None:
    """A name with no cv2 property is a gap here, not a fault in the device.

    Left unchecked it empties the readback and earns the "this device reported no controls at
    all" refusal, which sends the operator to `v4l2-ctl` and a camera that is working. The
    crossing between V4L2's names and cv2's property ids is written in this module, so a name
    missing from it is this module's to report.
    """
    cv2 = _cv2()
    capture = FakeCapture(_seeded(cv2))

    with pytest.raises(V4l2OpenError, match="focus_absolute"):
        _open(capture, controls=(CameraControl("focus_absolute", 30),))


def test_the_format_finding_survives_a_camera_with_nothing_declared() -> None:
    """The ZED-M is opened with no controls, and it is the camera this finding matters most for.

    The bandwidth budget is computed from the declared format's bytes per pixel, and the ZED-M
    carries the widest frame on this rig. A negotiated format that differs changes that
    arithmetic whether or not anyone declared an exposure for the camera.
    """
    cv2 = _cv2()
    capture = FakeCapture(
        _seeded(cv2), clamp={cv2.CAP_PROP_FOURCC: float(cv2.VideoWriter_fourcc(*"MJPG"))}
    )

    source = _open(capture, controls=())
    source.close()

    assert source.pixel_format_finding is not None
    assert "MJPG" in source.pixel_format_finding
