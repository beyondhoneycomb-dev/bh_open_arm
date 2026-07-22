"""A deterministic synthetic camera fixture with injectable drop and jitter.

`02b` §5.2 WP-3A-06 ①: 3B has no real hardware, so its camera-path tests run
against this fixture instead. Two properties make it a usable stand-in:

- Deterministic. A frame's bytes and its nominal capture instant are a pure
  function of `(slot, frame_index)` and the construction parameters, so a 3B
  test can assert an exact byte sequence and an exact timestamp, and a rerun
  reproduces them.
- Fault-injectable. A frame index can be marked *dropped* (the camera yields
  nothing for it, classified by the shared `CTR-PRIM@v1` queue semantics) and a
  per-frame timestamp *jitter* can be added, so the time-sync and tolerant-
  connection paths (`WP-3B-04`, `WP-3B-01`) have a fault to react to.

Every contract-shaped element — the slot identifier, the frame-type tag, the
channel count and dtype, the capture-timestamp domain, the drop classification —
is imported from `CTR-PRIM@v1` and never restated here (`02b` §5.0b). The frame
carries no resolution or fps in its identity; those live on the `CTR-CAM@v1`
`CameraSpec` alone.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field

from contracts.camera_registry import CameraSpec
from contracts.prim import (
    FRAME_TYPE_CHANNELS,
    FRAME_TYPE_DTYPE,
    QUEUE_PROFILES,
    REQUIRED_FRAME_TYPE,
    CameraSlotKey,
    CaptureTimestamp,
    DropClassification,
    FrameType,
)

# One nanosecond-per-second, named so the frame period is derived from the
# `CTR-CAM@v1` fps rather than a bare literal.
NANOS_PER_SECOND = 1_000_000_000

# The bytes-per-element of each frame dtype the frame-type primitive declares.
# Depth is uint16 (two bytes), RGB uint8 (one), so a frame's byte length is a
# function of the primitive's dtype, never a number this fixture invents.
_DTYPE_ITEMSIZE = {"uint8": 1, "uint16": 2}

# The queue class a live preview drop belongs to (`02b` §5.0b row 5): a preview
# drop is latest-wins and classified NORMAL, so an injected drop reads with the
# same meaning every consumer's quality report would give it.
_PREVIEW_QUEUE = QUEUE_PROFILES["camera_preview"]


def _dtype_itemsize(dtype: str) -> int:
    """Return the byte width of a frame dtype declared by `CTR-PRIM@v1`.

    Args:
        dtype: A `FRAME_TYPE_DTYPE` value.

    Returns:
        (int) Bytes per pixel element.
    """
    return _DTYPE_ITEMSIZE[dtype]


def _deterministic_bytes(seed: str, size: int) -> bytes:
    """Fill `size` bytes deterministically from a string seed.

    A SHA-256 keystream keyed by the seed gives a byte pattern that is stable
    across runs and machines yet varies per frame, so a test can pin exact bytes
    without a random-number generator whose stream could drift.

    Args:
        seed: The per-frame seed string.
        size: The number of bytes to produce.

    Returns:
        (bytes) Exactly `size` deterministic bytes.
    """
    out = bytearray()
    block = 0
    while len(out) < size:
        out.extend(hashlib.sha256(f"{seed}:{block}".encode()).digest())
        block += 1
    return bytes(out[:size])


@dataclass(frozen=True)
class SyntheticFrame:
    """One synthetic camera frame: its identity, capture instant and pixel bytes.

    Attributes:
        slot: The camera identifier, a `CTR-PRIM@v1` `CameraSlotKey`.
        frame_type: RGB or depth, the shared frame-type tag.
        frame_index: The 0-based frame position, the sidecar/dataset join key.
        capture_ts: The grab-time capture instant (nominal + injected jitter).
        width: Frame width in pixels, from the `CameraSpec` geometry.
        height: Frame height in pixels, from the `CameraSpec` geometry.
        data: The pixel bytes, length `width*height*channels*itemsize`.
    """

    slot: CameraSlotKey
    frame_type: FrameType
    frame_index: int
    capture_ts: CaptureTimestamp
    width: int
    height: int
    data: bytes

    @property
    def channels(self) -> int:
        """The channel count for this frame type, from `CTR-PRIM@v1`."""
        return FRAME_TYPE_CHANNELS[self.frame_type]

    @property
    def dtype(self) -> str:
        """The element dtype for this frame type, from `CTR-PRIM@v1`."""
        return FRAME_TYPE_DTYPE[self.frame_type]

    def ws_tag(self) -> str:
        """The `CTR-WS@v1` binary frame tag (`<slot>:<channel>`) for this frame.

        Derived through the `CTR-PRIM@v1` join, so a preview consumer recovers the
        exact slot the recorder and sidecar use.
        """
        return self.slot.ws_tag(self.frame_type)


@dataclass(frozen=True)
class SyntheticCamera:
    """A deterministic camera over one configured `CTR-CAM@v1` `CameraSpec`.

    The camera emits a frame per index at a nominal `CLOCK_MONOTONIC` instant
    `start_mono_ns + frame_index * period`, with an optional per-index jitter
    added and an optional set of indices dropped.

    Attributes:
        spec: The camera being simulated; must be configured (width/height/fps),
            because an unconfigured camera blocks collection start by contract.
        frame_type: The channel this camera emits (RGB by default).
        start_mono_ns: The capture instant of frame 0, monotonic nanoseconds.
        dropped_indices: Frame indices the camera yields nothing for.
        jitter_ns: Per-index nanosecond offset added to the nominal capture time.
    """

    spec: CameraSpec
    frame_type: FrameType = REQUIRED_FRAME_TYPE
    start_mono_ns: int = 0
    dropped_indices: frozenset[int] = field(default_factory=frozenset)
    jitter_ns: Mapping[int, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Reject an unconfigured camera or a frame type the camera does not offer."""
        if not self.spec.is_configured:
            raise ValueError(
                f"camera {self.spec.slot.value!r} is not configured (width/height/fps); "
                "an unconfigured camera cannot start collection (CTR-CAM@v1)"
            )
        if self.frame_type not in self.spec.capabilities:
            raise ValueError(
                f"camera {self.spec.slot.value!r} does not offer {self.frame_type.value}; "
                f"its capabilities are {sorted(c.value for c in self.spec.capabilities)}"
            )

    @property
    def slot(self) -> CameraSlotKey:
        """The camera identifier this camera emits under."""
        return self.spec.slot

    def frame_period_ns(self) -> int:
        """The nominal inter-frame interval in nanoseconds, derived from fps."""
        assert self.spec.fps is not None  # is_configured guarantees this
        return NANOS_PER_SECOND // self.spec.fps

    def nominal_capture_ns(self, frame_index: int) -> int:
        """The capture instant of a frame before jitter, monotonic nanoseconds.

        Args:
            frame_index: The 0-based frame position.

        Returns:
            (int) `start_mono_ns + frame_index * period`.
        """
        return self.start_mono_ns + frame_index * self.frame_period_ns()

    def is_dropped(self, frame_index: int) -> bool:
        """Whether this frame index was injected as a drop."""
        return frame_index in self.dropped_indices

    def drop_classification(self) -> DropClassification:
        """The shared meaning of a preview drop (`CTR-PRIM@v1`): NORMAL, latest-wins."""
        return _PREVIEW_QUEUE.drop_classification

    def read(self, frame_index: int) -> SyntheticFrame | None:
        """Grab one frame, or None when this index was dropped.

        The pixel bytes and the capture instant are deterministic in
        `(slot, frame_index)`; the capture instant additionally carries any
        injected jitter for this index.

        Args:
            frame_index: The 0-based frame position to grab.

        Returns:
            (SyntheticFrame | None) The frame, or None when injected as a drop.
        """
        if self.is_dropped(frame_index):
            return None
        assert self.spec.width is not None and self.spec.height is not None
        size = (
            self.spec.width
            * self.spec.height
            * FRAME_TYPE_CHANNELS[self.frame_type]
            * (_dtype_itemsize(FRAME_TYPE_DTYPE[self.frame_type]))
        )
        seed = f"{self.slot.value}:{self.frame_type.value}:{frame_index}"
        capture_ns = self.nominal_capture_ns(frame_index) + int(self.jitter_ns.get(frame_index, 0))
        return SyntheticFrame(
            slot=self.slot,
            frame_type=self.frame_type,
            frame_index=frame_index,
            capture_ts=CaptureTimestamp(mono_ns=capture_ns),
            width=self.spec.width,
            height=self.spec.height,
            data=_deterministic_bytes(seed, size),
        )

    def read_latest(self, up_to_index: int) -> SyntheticFrame | None:
        """Return the most recent non-dropped frame at or before an index.

        This is the non-blocking `read_latest()` the preview path uses
        (`02b` §6.2 WP-3B-06): under load it never blocks capture, it returns the
        freshest available frame and lets older ones fall away.

        Args:
            up_to_index: The newest index to consider.

        Returns:
            (SyntheticFrame | None) The latest live frame, or None when every index
                up to and including `up_to_index` was dropped.
        """
        for frame_index in range(up_to_index, -1, -1):
            frame = self.read(frame_index)
            if frame is not None:
                return frame
        return None

    def frames(self, count: int) -> list[SyntheticFrame]:
        """Grab the live frames of a run, skipping the dropped indices.

        Args:
            count: The number of frame indices to walk (0..count-1).

        Returns:
            (list[SyntheticFrame]) The frames that were not dropped, in order.
        """
        grabbed = [self.read(index) for index in range(count)]
        return [frame for frame in grabbed if frame is not None]

    def dropped(self, count: int) -> list[int]:
        """The dropped indices within a run, in ascending order.

        Args:
            count: The number of frame indices in the run.

        Returns:
            (list[int]) The indices of 0..count-1 that were dropped.
        """
        return [index for index in range(count) if self.is_dropped(index)]
