"""WP-3B-06 pipe: read-latest in, encode, TX-only out — never block capture.

These exercise the `02b` §6.2 acceptance criteria against the synthetic fixture:
① a busy link drops the preview frame and never blocks capture; ② preview
parameters are independent of the recording; ③ preview OFF costs zero encode and
zero transmit; and the read is `read_latest()` only, a dead camera warns-and-skips,
and a preview leaves only through the single WebSocket sink.
"""

from __future__ import annotations

import logging

import cv2
import numpy as np
import pytest

from backend.sensing.preview.encode import DepthEncoding
from backend.sensing.preview.frame import parse_ws_binary
from backend.sensing.preview.pipe import PreviewConfig, PreviewPipe, PreviewService
from contracts.prim import CameraSlotKey, FrameType
from contracts.ws import BUFFERED_AMOUNT_THRESHOLD_BYTES
from tests.wp3b06.support import (
    BlockingTrapSource,
    DeadSource,
    FakeSink,
    SyntheticSource,
    make_camera,
)


def _pipe(source: object, sink: FakeSink, **config_kwargs: object) -> PreviewPipe:
    return PreviewPipe(
        slot=CameraSlotKey("front"),
        source=source,  # type: ignore[arg-type]  # test doubles satisfy the protocol structurally
        sink=sink,
        config=PreviewConfig(**config_kwargs) if config_kwargs else PreviewConfig(),  # type: ignore[arg-type]
    )


def test_runs_here_1_frame_becomes_a_single_ws_binary_jpeg() -> None:
    """A polled frame downscales, imencodes to JPEG, and ships as one tagged WS binary (①)."""
    sink = FakeSink()
    pipe = _pipe(SyntheticSource(make_camera("front", FrameType.RGB, 1280, 720)), sink)

    preview = pipe.run_once(master_enabled=True)

    assert preview is not None
    assert len(sink.sent) == 1
    parsed = parse_ws_binary(sink.sent[0])
    assert parsed.slot == CameraSlotKey("front")
    assert parsed.channel is FrameType.RGB
    decoded = cv2.imdecode(np.frombuffer(parsed.payload, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert decoded is not None
    assert decoded.shape == (360, 640, 3)


def test_runs_here_2_pipe_reads_latest_only_never_a_blocking_read() -> None:
    """The pipe polls `read_latest()` and never reaches for a blocking read (②-RUNS)."""
    frame = make_camera("front").read(0)
    assert frame is not None
    trap = BlockingTrapSource(frame)

    _pipe(trap, FakeSink()).run_once(master_enabled=True)

    assert trap.read_latest_calls == 1


def test_runs_here_3_preview_off_costs_zero_encode_and_transmit() -> None:
    """A disabled pipe does not read, encode, or transmit (③)."""
    sink = FakeSink()
    source = SyntheticSource(make_camera("front"))
    pipe = _pipe(source, sink)
    pipe.enabled = False

    assert pipe.run_once(master_enabled=True) is None
    assert source.read_latest_calls == 0
    assert sink.sent == []
    counters = pipe.counters()
    assert counters.encoded == 0
    assert counters.transmitted == 0


def test_master_switch_off_stops_the_whole_service() -> None:
    """`PreviewService` with the master switch off does no work across every camera (③)."""
    sink = FakeSink()
    service = PreviewService(sink)
    left = SyntheticSource(make_camera("left_wrist"))
    right = SyntheticSource(make_camera("right_wrist"))
    service.register(CameraSlotKey("left_wrist"), left)
    service.register(CameraSlotKey("right_wrist"), right)

    service.enabled = False
    assert service.pump() == []
    assert left.read_latest_calls == 0
    assert right.read_latest_calls == 0
    assert sink.sent == []
    assert service.counters().encoded == 0


def test_master_switch_on_transmits_every_enabled_camera() -> None:
    """With the master switch on, each enabled camera transmits one preview per pump."""
    sink = FakeSink()
    service = PreviewService(sink)
    service.register(CameraSlotKey("left_wrist"), SyntheticSource(make_camera("left_wrist")))
    service.register(CameraSlotKey("right_wrist"), SyntheticSource(make_camera("right_wrist")))

    sent = service.pump()

    assert {frame.slot.value for frame in sent} == {"left_wrist", "right_wrist"}
    assert service.counters().transmitted == 2


def test_per_camera_disable_leaves_the_others_running() -> None:
    """Disabling one camera stops only its preview; siblings keep transmitting."""
    sink = FakeSink()
    service = PreviewService(sink)
    service.register(CameraSlotKey("left_wrist"), SyntheticSource(make_camera("left_wrist")))
    service.register(CameraSlotKey("right_wrist"), SyntheticSource(make_camera("right_wrist")))

    service.set_camera_enabled(CameraSlotKey("left_wrist"), False)
    sent = service.pump()

    assert {frame.slot.value for frame in sent} == {"right_wrist"}


def test_backpressure_drops_the_frame_without_encoding_or_blocking() -> None:
    """Over the WS buffer threshold the frame is dropped before encode/transmit (①)."""
    sink = FakeSink(buffered=BUFFERED_AMOUNT_THRESHOLD_BYTES + 1)
    source = SyntheticSource(make_camera("front"))
    pipe = _pipe(source, sink)

    assert pipe.run_once(master_enabled=True) is None
    assert sink.sent == []
    counters = pipe.counters()
    assert counters.dropped == 1
    assert counters.encoded == 0
    assert counters.transmitted == 0
    # The camera was still polled exactly once, non-blocking — capture is never stalled.
    assert source.read_latest_calls == 1


def test_below_threshold_the_frame_is_encoded_and_transmitted() -> None:
    """At the buffer threshold (not over it) the preview is encoded and sent."""
    sink = FakeSink(buffered=BUFFERED_AMOUNT_THRESHOLD_BYTES)
    pipe = _pipe(SyntheticSource(make_camera("front")), sink)

    assert pipe.run_once(master_enabled=True) is not None
    assert len(sink.sent) == 1
    assert pipe.counters().transmitted == 1


def test_dead_camera_warns_and_skips_without_failing(caplog: pytest.LogCaptureFixture) -> None:
    """A camera that yields nothing warns and skips; it never raises (read-only skip)."""
    sink = FakeSink()
    source = DeadSource()
    pipe = _pipe(source, sink)

    with caplog.at_level(logging.WARNING, logger="backend.sensing.preview.pipe"):
        result = pipe.run_once(master_enabled=True)

    assert result is None
    assert sink.sent == []
    counters = pipe.counters()
    assert counters.skipped == 1
    assert counters.encoded == 0
    assert counters.transmitted == 0
    assert any("no frame" in record.message for record in caplog.records)


def test_acceptance_2_preview_params_do_not_change_the_source_frame() -> None:
    """Changing preview parameters changes the preview, not the recording truth (②).

    Two configs render the same camera frame at different sizes, yet the source's
    own frame bytes — the value the recorder path would store — are identical, so a
    preview-parameter change never reaches a recording parameter.
    """
    camera = make_camera("front", FrameType.RGB, 1280, 720)
    truth_before = camera.read(0)
    assert truth_before is not None

    small = _pipe(SyntheticSource(camera), FakeSink(), max_long_edge_px=320)
    large = _pipe(SyntheticSource(camera), FakeSink(), max_long_edge_px=640)
    small_preview = small.run_once(master_enabled=True)
    large_preview = large.run_once(master_enabled=True)

    assert small_preview is not None and large_preview is not None
    assert small_preview.payload != large_preview.payload
    truth_after = camera.read(0)
    assert truth_after is not None
    assert truth_after.data == truth_before.data


def test_config_default_depth_encoding_is_a_valid_mode() -> None:
    """The default preview config selects a real depth encoding, not an unset value."""
    assert PreviewConfig().depth_encoding in set(DepthEncoding)
