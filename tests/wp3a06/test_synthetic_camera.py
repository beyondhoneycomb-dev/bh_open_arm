"""The synthetic camera: deterministic frames, injected drops and jitter (WP-3A-06 ①).

`02b` §5.2 WP-3A-06 ①: the camera must emit deterministic frames and take injected
drop and jitter. These tests pin all three — byte-exact reproducibility, a dropped
index yielding nothing, and a jittered index landing off its nominal grid — and check
that the frame carries the `CTR-PRIM@v1`/`CTR-CAM@v1` shapes rather than its own.
"""

from __future__ import annotations

from contracts.fixtures.synthetic_camera import SyntheticCamera
from contracts.fixtures.synthetic_dataset import default_camera_specs
from contracts.prim import (
    FRAME_TYPE_CHANNELS,
    FRAME_TYPE_DTYPE,
    REQUIRED_FRAME_TYPE,
    DropClassification,
    TimestampDomain,
    slot_from_ws_tag,
)

SPEC = default_camera_specs()[0]


def test_frames_are_byte_deterministic() -> None:
    """Two cameras built the same way emit byte-identical frames and timestamps."""
    a = SyntheticCamera(spec=SPEC, start_mono_ns=1000)
    b = SyntheticCamera(spec=SPEC, start_mono_ns=1000)
    for index in range(6):
        assert a.read(index) == b.read(index)


def test_frame_size_and_shape_come_from_the_primitive() -> None:
    """A frame's byte length is width*height*channels*itemsize from CTR-PRIM, not restated."""
    frame = SyntheticCamera(spec=SPEC).read(0)
    assert frame is not None
    channels = FRAME_TYPE_CHANNELS[REQUIRED_FRAME_TYPE]
    itemsize = 1 if FRAME_TYPE_DTYPE[REQUIRED_FRAME_TYPE] == "uint8" else 2
    assert len(frame.data) == frame.width * frame.height * channels * itemsize
    assert frame.channels == channels
    assert frame.dtype == FRAME_TYPE_DTYPE[REQUIRED_FRAME_TYPE]


def test_capture_ts_is_a_real_capture_instant() -> None:
    """The frame's capture_ts is a CTR-PRIM CaptureTimestamp in the capture domain."""
    frame = SyntheticCamera(spec=SPEC, start_mono_ns=5000).read(0)
    assert frame is not None
    assert frame.capture_ts.mono_ns == 5000
    assert frame.capture_ts.domain == TimestampDomain.CAPTURE


def test_injected_drop_yields_nothing_and_is_classified() -> None:
    """A dropped index returns None, is reported in the run, and carries the shared drop class."""
    cam = SyntheticCamera(spec=SPEC, dropped_indices=frozenset({2, 4}))
    assert cam.read(2) is None
    assert cam.read(4) is None
    assert cam.read(3) is not None
    assert [f.frame_index for f in cam.frames(6)] == [0, 1, 3, 5]
    assert cam.dropped(6) == [2, 4]
    assert cam.drop_classification() == DropClassification.NORMAL


def test_read_latest_skips_a_dropped_tail() -> None:
    """read_latest returns the freshest live frame, walking back past drops."""
    cam = SyntheticCamera(spec=SPEC, dropped_indices=frozenset({4, 5}))
    assert cam.read_latest(5).frame_index == 3
    assert cam.read_latest(3).frame_index == 3


def test_injected_jitter_shifts_only_the_named_index() -> None:
    """Jitter adds to a frame's capture instant at its index; other frames stay on the grid."""
    cam = SyntheticCamera(spec=SPEC, start_mono_ns=0, jitter_ns={1: 777})
    assert cam.read(1).capture_ts.mono_ns == cam.nominal_capture_ns(1) + 777
    assert cam.read(0).capture_ts.mono_ns == cam.nominal_capture_ns(0)
    assert cam.read(2).capture_ts.mono_ns == cam.nominal_capture_ns(2)


def test_ws_tag_round_trips_the_camera_identifier() -> None:
    """The frame's WS binary tag recovers the exact slot through the CTR-PRIM join."""
    frame = SyntheticCamera(spec=SPEC).read(0)
    assert frame is not None
    assert slot_from_ws_tag(frame.ws_tag()) == frame.slot


def test_unconfigured_camera_cannot_emit() -> None:
    """An unconfigured CameraSpec (no width/height/fps) cannot back a camera."""
    from contracts.camera_registry import make_arm_camera

    unconfigured = make_arm_camera("left", "wrist", frozenset({REQUIRED_FRAME_TYPE}))
    try:
        SyntheticCamera(spec=unconfigured)
    except ValueError:
        return
    raise AssertionError("an unconfigured camera must not be constructable")
