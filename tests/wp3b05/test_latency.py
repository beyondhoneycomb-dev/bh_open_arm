"""WP-3B-05 ② — save_episode and transcode latencies are recorded at p50/p95.

`07` NFR-REC-005 measures two wall-clocks: the `save_episode()` call-to-return, and
the batch-transcode completion, each as p50/p95. These confirm both series are
recorded and read out, and that the non-blocking `save_episode()` (which only
finalizes and hands off) is fast — its p95 stays well under a transcode's runtime.
"""

from __future__ import annotations

from backend.sensing.encoding import (
    EncoderConfig,
    EncoderSettings,
    EpisodeEncodingPipeline,
    TranscodeWorker,
    percentile,
)
from backend.sensing.encoding.constants import PERCENTILE_P50, PERCENTILE_P95
from tests.wp3b05.support import ControllableTranscoder, ingest_episode, rgb_camera

_EPISODES = 6
# save_episode only finalizes and enqueues, so its p95 is far under a millisecond;
# this bound is generous and still separates it from any real transcode runtime.
_SAVE_P95_BOUND_NS = 100_000_000  # 100 ms


def test_percentile_matches_linear_interpolation():
    """The shared percentile helper interpolates between ranks."""
    assert percentile([10, 20, 30, 40], 50.0) == 25.0
    assert percentile([10], 95.0) == 10.0


def test_save_and_transcode_latencies_are_recorded(tmp_path):
    """Both latency series fill up over a run and expose p50/p95."""
    worker = TranscodeWorker(ControllableTranscoder())
    settings = EncoderSettings(EncoderConfig())
    pipeline = EpisodeEncodingPipeline(
        raw_root=tmp_path / "raw",
        output_root=tmp_path / "out",
        settings=settings,
        worker=worker,
    )
    try:
        for episode_index in range(_EPISODES):
            store = pipeline.begin_episode(episode_index)
            stream = ingest_episode(store, rgb_camera(), frame_count=2)
            pipeline.save_episode(store, [stream])
        assert worker.wait_idle(timeout=10.0)

        assert pipeline.save_latency().count() == _EPISODES
        assert worker.transcode_latency_ns() != ()
        assert len(worker.transcode_latency_ns()) == _EPISODES

        save_p50 = pipeline.save_percentile(PERCENTILE_P50)
        save_p95 = pipeline.save_percentile(PERCENTILE_P95)
        assert save_p50 <= save_p95
        assert save_p95 < _SAVE_P95_BOUND_NS

        transcode_p50 = worker.transcode_percentile(PERCENTILE_P50)
        transcode_p95 = worker.transcode_percentile(PERCENTILE_P95)
        assert transcode_p50 <= transcode_p95
    finally:
        worker.close(timeout=5.0)
