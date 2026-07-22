"""The two-stage recording pipeline seam (`02b` §6.2 WP-3B-05 ②④).

This ties the three pieces together as the recorder sees them: the record-start
settings latch, the per-episode original store (stage 1), and the batch-transcode
worker (stage 2). It exists so `save_episode()` has one home and one measurable
latency — the `07` NFR-REC-005 figure that proves the design: the call finalizes the
episode and hands the transcode to the worker, then returns, so the next episode's
capture never waits on the previous transcode.

`begin_episode` latches the encoder settings (`02b` §6.2 WP-3B-05 ④): once the first
episode's originals start landing on disk, the encoder configuration is frozen for
the session.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from pathlib import Path

from backend.sensing.encoding.config import EncoderSettings
from backend.sensing.encoding.rawstore import RawEpisodeStore, RawStreamRef
from backend.sensing.encoding.worker import (
    LatencyRecorder,
    TranscodeJob,
    TranscodeWorker,
)


class EpisodeEncodingPipeline:
    """Stage-1 ingest plus stage-2 transcode dispatch, with save-episode latency.

    Ownership: holds the session's settings latch and the transcode worker; creates
    one `RawEpisodeStore` per episode under `raw_root`. It does not own the worker's
    thread lifecycle beyond dispatch — the caller closes the worker at session end.
    """

    def __init__(
        self,
        raw_root: Path,
        output_root: Path,
        settings: EncoderSettings,
        worker: TranscodeWorker,
    ) -> None:
        """Wire the pipeline to its stores and worker.

        Args:
            raw_root: Directory the per-episode original stores are created under.
            output_root: Directory the transcoded artifacts are written under.
            settings: The record-start settings latch.
            worker: The batch-transcode worker jobs are submitted to.
        """
        self._raw_root = raw_root
        self._output_root = output_root
        self._settings = settings
        self._worker = worker
        self._save_latency = LatencyRecorder()

    def begin_episode(self, episode_index: int) -> RawEpisodeStore:
        """Open the stage-1 original store for an episode and latch the settings.

        Args:
            episode_index: The 0-based episode to begin.

        Returns:
            (RawEpisodeStore) The store the episode's originals are written to.
        """
        self._settings.start_recording()
        return RawEpisodeStore(root=self._raw_root, episode_index=episode_index)

    def save_episode(self, store: RawEpisodeStore, streams: Sequence[RawStreamRef]) -> TranscodeJob:
        """Finalize an episode and hand its transcode to the worker, non-blocking.

        The measured span is exactly what `07` NFR-REC-005 records for the return
        latency: build the transcode job and submit it. The transcode itself runs
        later on the worker thread, so this returns without waiting on it.

        Args:
            store: The episode's stage-1 original store.
            streams: The camera streams recorded for the episode.

        Returns:
            (TranscodeJob) The job that was submitted, for the caller to track.
        """
        start_ns = time.perf_counter_ns()
        job = TranscodeJob(
            store=store,
            streams=tuple(streams),
            output_dir=self._output_root / f"episode_{store.episode_index:06d}",
        )
        self._worker.submit(job)
        self._save_latency.record(time.perf_counter_ns() - start_ns)
        return job

    def save_latency(self) -> LatencyRecorder:
        """The recorder of `save_episode()` return latencies (`07` NFR-REC-005)."""
        return self._save_latency

    def save_percentile(self, p: float) -> float:
        """The p-th percentile of `save_episode()` return latency, in nanoseconds.

        Args:
            p: The percentile in [0, 100].

        Returns:
            (float) The interpolated latency in nanoseconds.
        """
        return self._save_latency.percentile(p)
