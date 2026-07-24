"""Direct mp4 and per-frame-image decode — no Rerun, no dora replayer.

`FR-DAT-009`: the viewer reads parquet and mp4 itself. This module is the mp4
half — a PyAV reader that returns a single frame by its grid index, seeking to
`from_timestamp + index / fps` inside a packed video and decoding forward to the
nearest frame. A container is opened once per stream and reused across scrubs, so
a frame step is a seek and a short decode rather than a re-open (`NFR-DAT-001`).

Depth in v3.0 is stored as per-frame 16-bit TIFF images, not video; `read_image_frame`
covers that and the PNG still form. `VideoFrameReader` assumes an RGB stream —
the depth path never routes through it.
"""

from __future__ import annotations

from pathlib import Path

import av
import numpy as np
from numpy.typing import NDArray
from PIL import Image

from backend.dataset.viewer.channels import CameraStream
from backend.dataset.viewer.constants import (
    DEPTH_IMAGE_PATH_TEMPLATE,
    RGB_IMAGE_PATH_TEMPLATE,
)
from backend.dataset.viewer.layout import VideoSegment


class ViewerVideoError(ValueError):
    """Raised when a frame cannot be decoded from a video or image stream.

    A distinct type from a layout error: the file was located but its contents
    could not yield the requested frame (a truncated mp4, a missing image file).
    """


class VideoFrameReader:
    """A reusable single-frame decoder for one episode's segment of an mp4.

    Ownership/lifecycle: opens the container on construction and holds it until
    `close()`; not thread-safe — one reader serves one stream on one thread. Use
    as a context manager, or close explicitly, so the container is released.
    """

    def __init__(self, segment: VideoSegment, fps: int) -> None:
        """Open the mp4 for a stream's episode segment.

        Args:
            segment: The stream's mp4 file and `[from_timestamp, to_timestamp]`.
            fps: The dataset frame rate, mapping a grid index to a container time.

        Raises:
            ViewerVideoError: If the container cannot be opened or has no video stream.
        """
        self._segment = segment
        self._fps = fps
        try:
            self._container = av.open(str(segment.file))
        except Exception as bad:  # noqa: BLE001 — any av open failure is a corrupt/unreadable file
            raise ViewerVideoError(f"cannot open video {segment.file}: {bad}") from bad
        if not self._container.streams.video:
            self._container.close()
            raise ViewerVideoError(f"{segment.file} carries no video stream")
        self._stream = self._container.streams.video[0]
        self._stream.thread_type = "AUTO"

    def __enter__(self) -> VideoFrameReader:
        """Enter the reader's context."""
        return self

    def __exit__(self, *exc: object) -> None:
        """Release the open container on context exit."""
        self.close()

    def frame(self, frame_index: int) -> NDArray[np.uint8]:
        """Decode the RGB frame at a grid index.

        Seeks to `from_timestamp + frame_index / fps` (the packed-file offset the
        v3.0 read path uses) and decodes forward to the frame nearest that time.

        Args:
            frame_index: The episode-local grid index.

        Returns:
            (NDArray[np.uint8]) The frame as `(height, width, 3)` RGB.

        Raises:
            ViewerVideoError: If no frame could be decoded.
        """
        seconds = self._segment.from_timestamp + frame_index / self._fps
        time_base = self._stream.time_base
        target = int(round(seconds / time_base)) if time_base else int(round(seconds))
        self._container.seek(target, stream=self._stream, backward=True, any_frame=False)

        best: av.VideoFrame | None = None
        for decoded in self._container.decode(self._stream):
            if decoded.pts is None:
                continue
            if best is None or abs(decoded.pts - target) < abs(best.pts - target):
                best = decoded
            if decoded.pts >= target:
                break
        if best is None:
            raise ViewerVideoError(
                f"no frame decoded at index {frame_index} in {self._segment.file}"
            )
        return best.to_ndarray(format="rgb24")

    def close(self) -> None:
        """Close the open container."""
        self._container.close()


def read_image_frame(
    root: Path, stream: CameraStream, episode_index: int, frame_index: int
) -> NDArray[np.generic]:
    """Read one frame of an image-sequence stream (depth TIFF or RGB PNG).

    Args:
        root: The dataset root.
        stream: The camera stream (its frame type selects the path template).
        episode_index: The episode the frame belongs to.
        frame_index: The episode-local grid index.

    Returns:
        (NDArray) Depth as `(height, width)` uint16, or RGB as `(height, width, 3)`.

    Raises:
        ViewerVideoError: If the per-frame image file is missing or unreadable.
    """
    template = DEPTH_IMAGE_PATH_TEMPLATE if stream.is_depth else RGB_IMAGE_PATH_TEMPLATE
    path = root / template.format(
        image_key=stream.image_key, episode_index=episode_index, frame_index=frame_index
    )
    if not path.is_file():
        raise ViewerVideoError(f"image frame {path} is missing")
    try:
        with Image.open(path) as image:
            return np.asarray(image)
    except Exception as bad:  # noqa: BLE001 — any PIL failure is an unreadable-image signal
        raise ViewerVideoError(f"cannot read image frame {path}: {bad}") from bad
