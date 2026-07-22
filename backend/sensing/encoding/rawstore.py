"""Stage-1 raw ingest: lossless originals to disk (`02b` §6.2 WP-3B-05 ①).

During collection the two-stage pipeline records the *original* frame, never a
transcoded one (`15` NFR-PRF-028): RGB as lossless PNG, depth as 16-bit TIFF
(`06` §2.8, `datasets/utils.py:82-98`). The channel count and element type of each
frame kind are the frozen `CTR-PRIM@v1` frame-type facts (`FRAME_TYPE_CHANNELS`,
`FRAME_TYPE_DTYPE`); this module reads them and never restates a depth channel as
anything other than one uint16 plane.

The store lays originals out under `<root>/episode_<index>/<image-key>/frame-*.ext`,
keyed by the `CTR-PRIM@v1` slot image/depth key so the on-disk stream carries the
same identifier the sidecar and dataset join on. Stage 2 (the transcode worker)
reads these files back; nothing here encodes to a video format — that is the
worker's injected transcoder, whose production codec is WP-3C-02.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from backend.sensing.encoding.constants import (
    DEPTH_FILE_PATTERN,
    IMAGE_FILE_PATTERN,
    PNG_COMPRESSION_LEVEL,
)
from contracts.prim import (
    FRAME_TYPE_CHANNELS,
    FRAME_TYPE_DTYPE,
    CameraSlotKey,
    FrameType,
)


class RawIngestError(ValueError):
    """Raised when a frame array does not match its `CTR-PRIM@v1` frame-type shape.

    A frame handed to stage-1 ingest must already be the contract shape — RGB is
    three-channel uint8, depth is single-channel uint16 — because the on-disk
    original is the ground truth the transcode is later checked against.
    """


@dataclass(frozen=True)
class RawStreamRef:
    """Identity of one recorded stream: a camera slot and its frame kind.

    Attributes:
        slot: The camera identifier, a `CTR-PRIM@v1` slot key.
        frame_type: RGB or depth; fixes the on-disk format and the array shape.
    """

    slot: CameraSlotKey
    frame_type: FrameType

    def dataset_key(self) -> str:
        """The `CTR-PRIM@v1` feature key this stream's directory is named after.

        Returns:
            (str) `observation.images.<slot>` for RGB, `<slot>_depth` for depth.
        """
        if self.frame_type == FrameType.DEPTH:
            return self.slot.depth_key()
        return self.slot.image_key()

    def file_pattern(self) -> str:
        """The frame-file name pattern for this stream's frame kind."""
        return DEPTH_FILE_PATTERN if self.frame_type == FrameType.DEPTH else IMAGE_FILE_PATTERN


def _expect_shape(frame_type: FrameType, array: np.ndarray) -> np.ndarray:
    """Validate an array against the frozen frame-type shape and return it normalized.

    Depth is accepted as `(H, W)` or `(H, W, 1)` and normalized to `(H, W)` for the
    single-plane TIFF; RGB must be `(H, W, 3)`. The element type must match the
    `CTR-PRIM@v1` dtype exactly — a uint8 depth frame is a contract violation, not a
    value to silently upcast.

    Args:
        frame_type: The declared frame kind.
        array: The pixel array to validate.

    Returns:
        (np.ndarray) The validated, C-contiguous array (depth squeezed to 2-D).

    Raises:
        RawIngestError: If the dtype or channel count is not the contract shape.
    """
    expected_dtype = FRAME_TYPE_DTYPE[frame_type]
    if array.dtype != np.dtype(expected_dtype):
        raise RawIngestError(
            f"{frame_type.value} frame dtype {array.dtype} is not the contract "
            f"{expected_dtype} (CTR-PRIM@v1 FRAME_TYPE_DTYPE)"
        )
    channels = FRAME_TYPE_CHANNELS[frame_type]
    if frame_type == FrameType.DEPTH:
        if array.ndim == 3 and array.shape[2] == 1:
            array = array[:, :, 0]
        if array.ndim != 2:
            raise RawIngestError(
                f"depth frame must be single-channel (H, W)[, 1]; got shape {array.shape}"
            )
    elif array.ndim != 3 or array.shape[2] != channels:
        raise RawIngestError(f"rgb frame must be (H, W, {channels}); got shape {array.shape}")
    return np.ascontiguousarray(array)


def encode_frame(frame_type: FrameType, array: np.ndarray) -> bytes:
    """Encode one frame to its lossless original byte form (PNG or 16-bit TIFF).

    Args:
        frame_type: RGB (lossless PNG) or depth (16-bit TIFF).
        array: The pixel array in the frozen frame-type shape.

    Returns:
        (bytes) The encoded original.

    Raises:
        RawIngestError: If the array shape is wrong, or the codec fails to encode.
    """
    normalized = _expect_shape(frame_type, array)
    if frame_type == FrameType.DEPTH:
        ok, buffer = cv2.imencode(".tiff", normalized)
    else:
        ok, buffer = cv2.imencode(
            ".png", normalized, [cv2.IMWRITE_PNG_COMPRESSION, PNG_COMPRESSION_LEVEL]
        )
    if not ok:
        raise RawIngestError(f"failed to encode {frame_type.value} frame")
    return bytes(buffer)


def decode_frame(path: Path) -> np.ndarray:
    """Decode a stored original back to its pixel array (stage-2 read-back).

    Reads with `IMREAD_UNCHANGED` so a 16-bit depth plane returns as uint16 rather
    than being flattened to 8-bit.

    Args:
        path: The original file to read.

    Returns:
        (np.ndarray) The decoded pixel array.

    Raises:
        RawIngestError: If the file cannot be decoded.
    """
    array = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if array is None:
        raise RawIngestError(f"could not decode original {path}")
    return array


@dataclass(frozen=True)
class RawEpisodeStore:
    """The on-disk original tree for one episode's frames.

    Ownership: one store owns the `<root>/episode_<index>` directory for one
    episode. It is written only during that episode's capture; after the episode
    ends the transcode worker reads it and the recorder's integrity gate (WP-3C-06)
    decides when the originals may be cleaned.

    Attributes:
        root: The dataset root under which the per-episode directory is created.
        episode_index: The 0-based episode this store holds.
    """

    root: Path
    episode_index: int

    @property
    def episode_dir(self) -> Path:
        """The per-episode directory the originals are laid out under."""
        return self.root / f"episode_{self.episode_index:06d}"

    def stream_dir(self, stream: RawStreamRef) -> Path:
        """The directory holding one stream's frame files.

        Args:
            stream: The stream whose directory is named.

        Returns:
            (Path) `<episode_dir>/<dataset-key>`.
        """
        return self.episode_dir / stream.dataset_key()

    def frame_path(self, stream: RawStreamRef, frame_index: int) -> Path:
        """The path a given frame of a stream is stored at.

        Args:
            stream: The stream the frame belongs to.
            frame_index: The 0-based frame position.

        Returns:
            (Path) The frame file path, named by the stream's file pattern.
        """
        return self.stream_dir(stream) / stream.file_pattern().format(frame_index=frame_index)

    def ingest(self, stream: RawStreamRef, frame_index: int, array: np.ndarray) -> Path:
        """Write one original frame to disk and return its path.

        Args:
            stream: The stream the frame belongs to.
            frame_index: The 0-based frame position (the sidecar join key).
            array: The pixel array in the frozen frame-type shape.

        Returns:
            (Path) The written original's path.

        Raises:
            RawIngestError: If the frame does not match its contract shape.
        """
        encoded = encode_frame(stream.frame_type, array)
        path = self.frame_path(stream, frame_index)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(encoded)
        return path

    def frame_paths(self, stream: RawStreamRef) -> list[Path]:
        """The stored frame files of a stream, in frame order.

        Args:
            stream: The stream to list.

        Returns:
            (list[Path]) Frame file paths sorted by name (the zero-padded index).
        """
        directory = self.stream_dir(stream)
        if not directory.is_dir():
            return []
        return sorted(directory.iterdir())

    def frame_count(self, stream: RawStreamRef) -> int:
        """The number of originals stored for a stream.

        Args:
            stream: The stream to count.

        Returns:
            (int) The stored frame count.
        """
        return len(self.frame_paths(stream))
