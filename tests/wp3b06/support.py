"""Shared test doubles for the WP-3B-06 preview-pipe tests.

The real frame data comes from the frozen `WP-3A-06` synthetic camera fixture
(the 3B test target): `synthetic_source` wraps it in the non-blocking
`LatestFrameSource` shape the pipe consumes. The remaining doubles are the fakes a
test needs to force a condition the fixture cannot inject on its own — a saturated
sink, a dead camera, a source that would explode if a blocking read were called.
"""

from __future__ import annotations

from contracts.camera_registry import CameraSpec
from contracts.fixtures.synthetic_camera import SyntheticCamera, SyntheticFrame
from contracts.prim import CameraSlotKey, FrameType

# A small default geometry stays under the preview downscale target, so a
# round-trip test sees no resize; tests that want the downscale path pass a larger
# one explicitly.
SMALL_WIDTH = 8
SMALL_HEIGHT = 8
DEFAULT_FPS = 30


def make_camera(
    slot_name: str,
    frame_type: FrameType = FrameType.RGB,
    width: int = SMALL_WIDTH,
    height: int = SMALL_HEIGHT,
) -> SyntheticCamera:
    """Build a configured synthetic camera for one slot and channel."""
    capabilities = {FrameType.RGB, frame_type}
    spec = CameraSpec(
        slot=CameraSlotKey(slot_name),
        capabilities=frozenset(capabilities),
        width=None,
        height=None,
        fps=None,
    ).configured(width, height, DEFAULT_FPS)
    return SyntheticCamera(spec=spec, frame_type=frame_type)


class SyntheticSource:
    """Adapt the synthetic camera to the non-blocking `LatestFrameSource` surface.

    Each `read_latest()` returns the freshest frame at the current index and
    advances the clock, mirroring a live camera the preview polls latest-wins.
    """

    def __init__(self, camera: SyntheticCamera, start_index: int = 0) -> None:
        self._camera = camera
        self._index = start_index
        self.read_latest_calls = 0

    def read_latest(self) -> SyntheticFrame | None:
        self.read_latest_calls += 1
        frame = self._camera.read_latest(self._index)
        self._index += 1
        return frame


class DeadSource:
    """A camera that never yields a frame — the warn-and-skip case."""

    def __init__(self) -> None:
        self.read_latest_calls = 0

    def read_latest(self) -> SyntheticFrame | None:
        self.read_latest_calls += 1
        return None


class BlockingTrapSource:
    """A source whose only safe read is `read_latest()`; any blocking read explodes.

    The pipe must read latest-wins and non-blocking; if it ever reached for a
    blocking read (`read`/`async_read`), that is the `WP-3B-06` `FAIL_BLOCKING`
    defect, and these traps turn it into a loud test failure.
    """

    def __init__(self, frame: SyntheticFrame) -> None:
        self._frame = frame
        self.read_latest_calls = 0

    def read_latest(self) -> SyntheticFrame | None:
        self.read_latest_calls += 1
        return self._frame

    def read(self) -> SyntheticFrame | None:
        raise AssertionError("pipe called a blocking read(); it must use read_latest() only")

    def async_read(self) -> SyntheticFrame | None:
        raise AssertionError("pipe used the recorder read path; preview is read_latest() only")


class FakeSink:
    """A TX-only sink that records sent frames and reports a settable buffer level."""

    def __init__(self, buffered: int = 0) -> None:
        self.buffered = buffered
        self.sent: list[bytes] = []

    def buffered_amount(self) -> int:
        return self.buffered

    def send_binary(self, data: bytes) -> None:
        self.sent.append(data)
