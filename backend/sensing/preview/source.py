"""The read-only camera side of the preview pipe (WP-3B-06).

The preview is READ-ONLY on the camera: it may observe the freshest frame and
nothing else. That guarantee is structural here, not a convention — the source a
pipe accepts exposes exactly one method, `read_latest()`, and it is non-blocking
by contract. There is deliberately no `read()`/`async_read()` on this surface: a
blocking read that stalls the preview loop until the next grab is the `WP-3B-06`
`FAIL_BLOCKING` defect (`02b` §6.2), because a stalled preview loop is a preview
that can back-pressure capture. The recorder reads through its own `async_read()`
(`02b` §6.2 "프리뷰는 read_latest()만, 기록은 async_read()"); the two never share a
read path.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from contracts.prim import CameraSlotKey, FrameType


@runtime_checkable
class PreviewSourceFrame(Protocol):
    """One grabbed frame as the preview needs to see it — identity plus raw pixels.

    This is the structural shape the `WP-3A-06` synthetic camera frame already
    satisfies, so a test frame and a real capture frame flow through the same
    encode path. The channel count and dtype are not carried here: they are a pure
    function of `frame_type` through `CTR-PRIM@v1` (`FRAME_TYPE_CHANNELS`/
    `FRAME_TYPE_DTYPE`), so the frame cannot disagree with the primitive about what
    an RGB or a depth buffer contains.

    Attributes:
        slot: The camera identifier this frame belongs to.
        frame_type: The channel (RGB or depth) the raw bytes hold.
        width: Frame width in pixels.
        height: Frame height in pixels.
        data: The raw pixel bytes, `width*height*channels*itemsize` long.
    """

    @property
    def slot(self) -> CameraSlotKey: ...

    @property
    def frame_type(self) -> FrameType: ...

    @property
    def width(self) -> int: ...

    @property
    def height(self) -> int: ...

    @property
    def data(self) -> bytes: ...


@runtime_checkable
class LatestFrameSource(Protocol):
    """A camera the preview reads latest-wins and non-blocking (`02b` §6.2).

    The one method is `read_latest()`: it returns the freshest available frame, or
    `None` when the camera has produced nothing (a dead or not-yet-ready camera).
    It must never block waiting for the next grab — under load the preview drops to
    the newest frame rather than stalling, which is what keeps the preview from
    ever back-pressuring the capture loop. Returning `None` is a warn-and-skip
    signal, never a failure: a dead preview camera does not fail arm connect or
    motion.
    """

    def read_latest(self) -> PreviewSourceFrame | None: ...
