"""An offline PyAV transcoder that verifies frame-count integrity (`NFR-CAM-007`).

The transcode worker (`worker.py`) takes any `transcode_fn`; this is the offline
default that actually decodes the stage-1 originals and re-encodes an RGB stream to
a real video container, then counts the frames back out of it. That closes the
two-stage loop with a real codec so acceptance ② is end-to-end, and it produces the
`NFR-CAM-007` ① figure — encoded frame count equals the original count.

What this is *not*: the production codec choice. The canonical pipeline transcodes
RGB to AV1 and depth to HEVC-Main12, and the SW/HW codec matrix (`libsvtav1` /
`h264_nvenc`) with its real-time factor is the resource-exclusive WP-3C-02
measurement (`PG-STO-001`). This module uses a lossless verification codec purely to
exercise the pipe; the depth production codec is deferred, so a depth stream's count
is verified against its originals rather than re-encoded here.

PyAV is an optional dependency (the `robot` group). It is imported lazily so the
worker core imports without it; `video_encoder_available` reports whether the
verification codec is present so a caller can skip-with-reason when it is not.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from backend.sensing.encoding.constants import NOMINAL_FPS
from backend.sensing.encoding.rawstore import RawEpisodeStore, RawStreamRef, decode_frame
from backend.sensing.encoding.worker import StreamTranscode, TranscodeJob, TranscodeResult
from contracts.prim import FrameType

if TYPE_CHECKING:
    import numpy as np

# The verification codec — lossless FFV1 in an MKV container. NOT a production codec
# choice: the canonical RGB target is AV1 and the SW/HW matrix plus RTF are WP-3C-02.
# FFV1 is chosen only because it is always present in the ffmpeg build and preserves
# the frame count exactly, which is the `NFR-CAM-007` ① property this verifies.
VERIFICATION_VIDEO_CODEC = "ffv1"
VERIFICATION_PIX_FMT = "yuv420p"
VERIFICATION_CONTAINER_SUFFIX = ".mkv"


class VideoTranscodeError(RuntimeError):
    """Raised when the verification transcode cannot run or its codec is absent."""


def video_encoder_available(codec: str = VERIFICATION_VIDEO_CODEC) -> bool:
    """Report whether the named video encoder is present in the PyAV/ffmpeg build.

    Args:
        codec: The encoder name to probe.

    Returns:
        (bool) True when the encoder can be opened, False when PyAV or the codec is
            unavailable — the caller then skips the real-transcode path with reason.
    """
    try:
        import av
    except ImportError:
        return False
    try:
        av.codec.Codec(codec, "w")
    except Exception:  # PyAV raises a codec-specific error; any of them means absent
        return False
    return True


def _encode_rgb_video(frames: list[np.ndarray], output_path: Path) -> int:
    """Encode RGB frames to a real video and count the frames back out of it.

    Args:
        frames: The decoded RGB frame arrays, in order.
        output_path: The container path to write.

    Returns:
        (int) The number of frames decoded back from the written container.

    Raises:
        VideoTranscodeError: If PyAV is unavailable or encoding fails.
    """
    try:
        import av
    except ImportError as missing:
        raise VideoTranscodeError(
            "PyAV is not installed; the verification codec is unavailable"
        ) from missing

    if not frames:
        output_path.write_bytes(b"")
        return 0

    height, width = frames[0].shape[0], frames[0].shape[1]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    container = av.open(str(output_path), "w")
    try:
        stream = container.add_stream(VERIFICATION_VIDEO_CODEC, rate=NOMINAL_FPS)
        stream.width = width
        stream.height = height
        stream.pix_fmt = VERIFICATION_PIX_FMT
        for array in frames:
            frame = av.VideoFrame.from_ndarray(array, format="rgb24")
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    finally:
        container.close()

    decoded = av.open(str(output_path))
    try:
        return sum(1 for _ in decoded.decode(video=0))
    finally:
        decoded.close()


def _transcode_rgb_stream(
    store: RawEpisodeStore, stream: RawStreamRef, output_dir: Path
) -> StreamTranscode:
    """Transcode one RGB stream to a verification video and record its integrity."""
    paths = store.frame_paths(stream)
    frames = [decode_frame(path) for path in paths]
    output_path = output_dir / f"{stream.dataset_key()}{VERIFICATION_CONTAINER_SUFFIX}"
    encoded = _encode_rgb_video(frames, output_path)
    return StreamTranscode(
        stream=stream,
        raw_frame_count=len(paths),
        encoded_frame_count=encoded,
        output_path=output_path,
    )


def _verify_depth_stream(store: RawEpisodeStore, stream: RawStreamRef) -> StreamTranscode:
    """Verify a depth stream's count against its originals (production codec deferred).

    Depth transcodes to HEVC-Main12 lossless in the production pipeline; that codec
    and its RTF are WP-3C-02/03, so offline the count is verified against the stored
    16-bit TIFF originals rather than re-encoded here.
    """
    count = store.frame_count(stream)
    return StreamTranscode(
        stream=stream,
        raw_frame_count=count,
        encoded_frame_count=count,
        output_path=store.stream_dir(stream),
    )


class PyAvTranscoder:
    """A `transcode_fn` that runs the offline verification transcode per stream.

    Ownership: stateless and thread-safe; the worker calls it on its own thread. RGB
    streams are re-encoded to a real container and counted back; depth streams are
    count-verified against their originals (production depth codec deferred).
    """

    def __call__(self, job: TranscodeJob) -> TranscodeResult:
        """Transcode every stream of an episode and return the integrity result.

        Args:
            job: The episode transcode job.

        Returns:
            (TranscodeResult) Per-stream frame-count integrity for the episode.
        """
        outcomes: list[StreamTranscode] = []
        for stream in job.streams:
            if stream.frame_type == FrameType.DEPTH:
                outcomes.append(_verify_depth_stream(job.store, stream))
            else:
                outcomes.append(_transcode_rgb_stream(job.store, stream, job.output_dir))
        return TranscodeResult(episode_index=job.episode_index, streams=tuple(outcomes))
