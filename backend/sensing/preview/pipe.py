"""The preview pipe: read latest, encode, transmit — never block capture (WP-3B-06).

This is where the `WP-3B-06` disciplines meet in one place (`02b` §6.2):

- READ-ONLY, non-blocking on the camera. A pipe reads through `read_latest()`
  only; there is no blocking read on the source surface at all, so the pipe can
  never stall the loop waiting for a grab — and a preview that cannot stall cannot
  back-pressure capture. A read that yields nothing (dead / not-ready camera) is a
  warn-and-skip, never a failure of arm connect or motion.
- Sheds under load rather than queuing. Before encoding, the pipe asks the sink
  for its `bufferedAmount` and drops the camera frame when the WS is over the
  `CTR-WS@v1` backpressure threshold, so a saturated link never delays a dead-man
  renewal and the wasted encode never happens.
- OFF means OFF. When preview is disabled — master switch or this camera's switch —
  the pipe returns before it reads, encodes, or transmits, so a disabled preview
  costs zero JPEG encodes and zero WS sends (`02b` §6.2 acceptance ③).
- One channel out. A preview leaves only through `PreviewSink.send_binary` on the
  single WebSocket; there is no second stream (`02b` §6.2 acceptance ④).

The preview parameters (`PreviewConfig`) are the pipe's own and touch no recording
parameter: a preview is orthogonal to the recording (`02b` §6.2 acceptance ②).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from backend.sensing.preview.constants import (
    JPEG_QUALITY_DEFAULT,
    JPEG_QUALITY_MAX,
    JPEG_QUALITY_MIN,
    PREVIEW_MAX_LONG_EDGE_PX,
)
from backend.sensing.preview.encode import DepthEncoding, encode_frame
from backend.sensing.preview.frame import PreviewFrame
from backend.sensing.preview.sink import PreviewSink
from backend.sensing.preview.source import LatestFrameSource
from contracts.prim import CameraSlotKey
from contracts.ws import WsFrameType, should_drop_under_backpressure

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PreviewConfig:
    """The preview-only encode parameters — independent of any recording parameter.

    Attributes:
        max_long_edge_px: The longest edge a preview frame is downscaled to.
        jpeg_quality: libjpeg quality (0..100) for JPEG payloads.
        depth_encoding: Whether depth previews as lossless PNG16 or a colormap.
    """

    max_long_edge_px: int = PREVIEW_MAX_LONG_EDGE_PX
    jpeg_quality: int = JPEG_QUALITY_DEFAULT
    depth_encoding: DepthEncoding = DepthEncoding.COLORMAP

    def __post_init__(self) -> None:
        """Reject a non-positive downscale target or an out-of-range JPEG quality."""
        if self.max_long_edge_px <= 0:
            raise ValueError(f"max_long_edge_px must be positive, got {self.max_long_edge_px}")
        if not JPEG_QUALITY_MIN <= self.jpeg_quality <= JPEG_QUALITY_MAX:
            raise ValueError(
                f"jpeg_quality must be in [{JPEG_QUALITY_MIN}, {JPEG_QUALITY_MAX}], "
                f"got {self.jpeg_quality}"
            )


@dataclass(frozen=True)
class PreviewCounters:
    """A point-in-time snapshot of what a pipe did, split by outcome.

    The four outcomes are kept apart because they mean different things: an encode
    and a transmit are work done; a drop is backpressure shedding (healthy,
    latest-wins); a skip is a camera that gave no frame (warn-and-skip). A GUI
    reads these to tell "the link is busy" from "the camera is dead".

    Attributes:
        encoded: Frames downscaled and encoded.
        transmitted: Frames sent on the WebSocket.
        dropped: Frames shed by backpressure before encoding.
        skipped: Polls where the camera yielded no frame.
    """

    encoded: int = 0
    transmitted: int = 0
    dropped: int = 0
    skipped: int = 0


@dataclass
class PreviewPipe:
    """One camera channel's preview: read-latest, encode, transmit, or shed.

    The pipe holds a non-blocking `LatestFrameSource` (read-only on the camera) and
    a `PreviewSink` (TX-only on the WS). It owns no recording state.

    Attributes:
        slot: The camera identifier this pipe previews.
        source: The non-blocking latest-frame source (read-only).
        sink: The single-WebSocket transmit surface (TX-only).
        config: The preview-only encode parameters.
        enabled: This camera's preview switch; independent of the master switch.
    """

    slot: CameraSlotKey
    source: LatestFrameSource
    sink: PreviewSink
    config: PreviewConfig = field(default_factory=PreviewConfig)
    enabled: bool = True
    _encoded: int = field(default=0, init=False)
    _transmitted: int = field(default=0, init=False)
    _dropped: int = field(default=0, init=False)
    _skipped: int = field(default=0, init=False)

    def counters(self) -> PreviewCounters:
        """Return a snapshot of this pipe's per-outcome counts."""
        return PreviewCounters(
            encoded=self._encoded,
            transmitted=self._transmitted,
            dropped=self._dropped,
            skipped=self._skipped,
        )

    def run_once(self, master_enabled: bool) -> PreviewFrame | None:
        """Poll the camera once and transmit a preview, or do nothing.

        Order matters and is the crux of the WP: the enabled gate short-circuits
        before any read/encode/transmit (so OFF is truly free); the read is the
        one non-blocking `read_latest()`; a `None` read warns and skips; the
        backpressure check is *before* the encode, so a busy link costs no encode.

        Args:
            master_enabled: The service-wide preview switch. False forces this pipe
                idle regardless of its own `enabled`.

        Returns:
            (PreviewFrame | None) The transmitted frame, or None when the pipe was
                disabled, the camera gave nothing, or the link shed the frame.
        """
        if not (master_enabled and self.enabled):
            return None

        frame = self.source.read_latest()
        if frame is None:
            self._skipped += 1
            logger.warning("preview camera %r yielded no frame; skipping", self.slot.value)
            return None

        if should_drop_under_backpressure(WsFrameType.CAMERA, self.sink.buffered_amount()):
            self._dropped += 1
            return None

        encoded = encode_frame(
            frame,
            self.config.max_long_edge_px,
            self.config.jpeg_quality,
            self.config.depth_encoding,
        )
        self._encoded += 1
        preview = PreviewFrame.from_encoded(self.slot, encoded)
        self.sink.send_binary(preview.to_ws_binary())
        self._transmitted += 1
        return preview


class PreviewService:
    """The whole preview surface: a master switch over per-camera pipes.

    A single realtime channel carries every camera's preview (`CTR-WS@v1` D-2);
    this service holds one pipe per camera and one master switch. `pump()` runs a
    round over the registered pipes. When the master switch is off, `pump()` does
    no read, no encode and no transmit — the whole preview stops (`02b` §6.2
    acceptance ③), which is why "preview 전체 OFF" is a single boolean, not a
    per-camera sweep a caller could get half-wrong.
    """

    def __init__(self, sink: PreviewSink) -> None:
        """Start with the master switch on and no cameras registered.

        Args:
            sink: The single-WebSocket transmit surface shared by every pipe.
        """
        self.sink = sink
        self.enabled = True
        self._pipes: dict[str, PreviewPipe] = {}

    def register(
        self,
        slot: CameraSlotKey,
        source: LatestFrameSource,
        config: PreviewConfig | None = None,
        enabled: bool = True,
    ) -> PreviewPipe:
        """Register a camera's preview pipe, keyed by its slot.

        Args:
            slot: The camera identifier.
            source: The non-blocking latest-frame source.
            config: The preview parameters; a default `PreviewConfig` when omitted.
            enabled: This camera's initial preview switch.

        Returns:
            (PreviewPipe) The registered pipe.
        """
        pipe = PreviewPipe(
            slot=slot,
            source=source,
            sink=self.sink,
            config=config if config is not None else PreviewConfig(),
            enabled=enabled,
        )
        self._pipes[slot.value] = pipe
        return pipe

    def set_camera_enabled(self, slot: CameraSlotKey, enabled: bool) -> None:
        """Turn one camera's preview on or off without touching the others."""
        self._pipes[slot.value].enabled = enabled

    def pump(self) -> list[PreviewFrame]:
        """Run one preview round over the registered cameras.

        Returns:
            (list[PreviewFrame]) The frames transmitted this round, in registration
                order. Empty when the master switch is off or nothing was sent.
        """
        if not self.enabled:
            return []
        sent: list[PreviewFrame] = []
        for pipe in self._pipes.values():
            preview = pipe.run_once(self.enabled)
            if preview is not None:
                sent.append(preview)
        return sent

    def counters(self) -> PreviewCounters:
        """Return the per-outcome counts summed across every registered pipe."""
        totals = [pipe.counters() for pipe in self._pipes.values()]
        return PreviewCounters(
            encoded=sum(count.encoded for count in totals),
            transmitted=sum(count.transmitted for count in totals),
            dropped=sum(count.dropped for count in totals),
            skipped=sum(count.skipped for count in totals),
        )
