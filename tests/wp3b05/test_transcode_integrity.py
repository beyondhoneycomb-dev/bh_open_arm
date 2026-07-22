"""WP-3B-05 — end-to-end transcode preserves the frame count (`NFR-CAM-007` ①).

The offline default transcoder (`video.py`) actually decodes the stage-1 originals
and re-encodes an RGB stream to a real video container, then counts the frames back
out — so the two-stage loop is exercised with a real codec, not stubbed. The
integrity figure it produces is the `NFR-CAM-007` ① check the WP-3C-06 cleanup gate
later depends on: encoded frame count equals the original count.

The production SW/HW codec matrix (`libsvtav1` / `h264_nvenc`) and its real-time
factor are the resource-exclusive WP-3C-02 measurement (`PG-STO-001`); this uses a
lossless verification codec only. If that codec is not present in the ffmpeg build,
the real-encode path is skipped with reason rather than asserted.
"""

from __future__ import annotations

import pytest

from backend.sensing.encoding import (
    EncoderConfig,
    EncoderSettings,
    EpisodeEncodingPipeline,
    TranscodeWorker,
)
from backend.sensing.encoding.video import PyAvTranscoder, video_encoder_available
from tests.wp3b05.support import depth_camera, ingest_episode, rgb_camera, stream_of

pytestmark = pytest.mark.skipif(
    not video_encoder_available(),
    reason="verification video codec not present in this PyAV/ffmpeg build",
)


def _pipeline(tmp_path):
    """Wire a pipeline over the real PyAV verification transcoder."""
    worker = TranscodeWorker(PyAvTranscoder())
    settings = EncoderSettings(EncoderConfig())
    pipeline = EpisodeEncodingPipeline(
        raw_root=tmp_path / "raw",
        output_root=tmp_path / "out",
        settings=settings,
        worker=worker,
    )
    return pipeline, worker


def test_rgb_transcode_preserves_frame_count(tmp_path):
    """A real RGB transcode produces exactly the number of frames it ingested."""
    pipeline, worker = _pipeline(tmp_path)
    try:
        store = pipeline.begin_episode(0)
        stream = ingest_episode(store, rgb_camera(), frame_count=8)
        pipeline.save_episode(store, [stream])
        assert worker.wait_idle(timeout=20.0)

        result = worker.result(0)
        assert result is not None
        assert worker.failure(0) is None
        outcome = result.streams[0]
        assert outcome.raw_frame_count == 8
        assert outcome.encoded_frame_count == 8
        assert outcome.frame_count_matches
        assert outcome.output_path.exists()
        assert outcome.output_path.stat().st_size > 0
    finally:
        worker.close(timeout=5.0)


def test_depth_stream_count_is_verified_against_originals(tmp_path):
    """A depth stream's count is verified against its 16-bit TIFF originals."""
    pipeline, worker = _pipeline(tmp_path)
    try:
        store = pipeline.begin_episode(0)
        camera = depth_camera()
        stream = ingest_episode(store, camera, frame_count=6)
        pipeline.save_episode(store, [stream])
        assert worker.wait_idle(timeout=20.0)

        result = worker.result(0)
        assert result is not None
        outcome = result.streams[0]
        assert outcome.stream == stream_of(camera)
        assert outcome.raw_frame_count == 6
        assert outcome.frame_count_matches
    finally:
        worker.close(timeout=5.0)
