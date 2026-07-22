"""WP-3B-05 ② — transcode runs after episode end, on a worker off the recording path.

The design guarantee (`07` NFR-REC-005): `save_episode()` finalizes and hands the
transcode to a separate worker, then returns — so starting the next episode never
waits on the previous transcode. These prove it by gating the transcode: while
episode 0's transcode is blocked inside the worker thread, episode 1's ingest and
`save_episode()` still complete, and the transcode is shown to run on a thread that
is not the caller's.
"""

from __future__ import annotations

import threading
import time

from backend.sensing.encoding import (
    EncoderConfig,
    EncoderSettings,
    EpisodeEncodingPipeline,
    TranscodeWorker,
)
from tests.wp3b05.support import ControllableTranscoder, ingest_episode, rgb_camera

# A save that has to wait on a transcode would take the gated transcode's full
# timeout; a non-blocking save returns far under it. The bound separates the two.
_NON_BLOCKING_BOUND_S = 1.0


def _build_pipeline(tmp_path, transcoder):
    """Wire a pipeline and its worker over a controllable transcoder."""
    worker = TranscodeWorker(transcoder, encoder_queue_maxsize=30)
    settings = EncoderSettings(EncoderConfig())
    pipeline = EpisodeEncodingPipeline(
        raw_root=tmp_path / "raw",
        output_root=tmp_path / "out",
        settings=settings,
        worker=worker,
    )
    return pipeline, worker


def test_save_episode_returns_while_transcode_still_running(tmp_path):
    """save_episode(1) returns while episode 0's transcode is still blocked."""
    gate = threading.Event()
    transcoder = ControllableTranscoder(gate=gate)
    pipeline, worker = _build_pipeline(tmp_path, transcoder)
    try:
        store0 = pipeline.begin_episode(0)
        stream0 = ingest_episode(store0, rgb_camera(), frame_count=3)
        pipeline.save_episode(store0, [stream0])

        # The worker picks up episode 0 and blocks inside the gated transcode.
        pickup_deadline = time.monotonic() + 2.0
        while transcoder.episodes != [0] and time.monotonic() < pickup_deadline:
            time.sleep(0.005)
        assert transcoder.episodes == [0]

        started = time.monotonic()
        store1 = pipeline.begin_episode(1)
        stream1 = ingest_episode(store1, rgb_camera("side"), frame_count=3)
        pipeline.save_episode(store1, [stream1])
        elapsed = time.monotonic() - started

        # Episode 1 finished its recording path without waiting on episode 0.
        assert elapsed < _NON_BLOCKING_BOUND_S
        assert worker.result(0) is None  # episode 0 transcode is still blocked
        assert worker.outstanding == 2  # both episodes outstanding

        gate.set()
        assert worker.wait_idle(timeout=5.0)
        assert worker.result(0) is not None
        assert worker.result(1) is not None
    finally:
        gate.set()
        worker.close(timeout=5.0)


def test_transcode_runs_on_a_different_thread(tmp_path):
    """The transcode executes on the worker thread, never the calling thread."""
    transcoder = ControllableTranscoder()
    pipeline, worker = _build_pipeline(tmp_path, transcoder)
    try:
        store = pipeline.begin_episode(0)
        stream = ingest_episode(store, rgb_camera(), frame_count=2)
        pipeline.save_episode(store, [stream])
        assert worker.wait_idle(timeout=5.0)

        assert transcoder.thread_idents  # the transcode actually ran
        assert threading.get_ident() not in transcoder.thread_idents
        assert transcoder.thread_idents[0] == worker.thread_ident
    finally:
        worker.close(timeout=5.0)


def test_result_preserves_frame_count(tmp_path):
    """The transcode result reports the raw frame count it was handed."""
    transcoder = ControllableTranscoder()
    pipeline, worker = _build_pipeline(tmp_path, transcoder)
    try:
        store = pipeline.begin_episode(0)
        stream = ingest_episode(store, rgb_camera(), frame_count=5)
        pipeline.save_episode(store, [stream])
        assert worker.wait_idle(timeout=5.0)

        result = worker.result(0)
        assert result is not None
        assert result.frame_counts_match
        assert result.streams[0].raw_frame_count == 5
    finally:
        worker.close(timeout=5.0)
