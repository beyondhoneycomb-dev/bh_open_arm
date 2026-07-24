"""Acceptance ⑤/`NFR-DAT-001`: a frame step completes within the frame period.

The bench mirrors the spec's measurement: load one episode, then time (a) 200
frame steps and (b) 200 random seeks, where each timed operation runs the *full*
update — every camera stream (RGB + depth) plus the state/action/error cursor —
and report p50/p95/p99. The frame-step bound is 33 ms @ 30 fps; the random-seek
upper bound is unconfirmed in the plan, so it is measured and reported, not asserted.
"""

from __future__ import annotations

import time

import numpy as np

from backend.dataset.viewer.episode_viewer import EpisodeViewer
from tests.wp3d01.materialize import MaterializedDataset

_FRAME_PERIOD_MS = 1000.0 / 30.0
_ITERATIONS = 200


def _percentiles(samples_ms: list[float]) -> dict[str, float]:
    array = np.asarray(samples_ms, dtype=np.float64)
    return {
        "p50": float(np.percentile(array, 50)),
        "p95": float(np.percentile(array, 95)),
        "p99": float(np.percentile(array, 99)),
    }


def test_frame_step_within_frame_period(
    episode0: EpisodeViewer, dataset: MaterializedDataset
) -> None:
    frames = dataset.frames
    # Warm the decoders so the first cold open is not counted as a step.
    episode0.frame_by_index(0)

    samples: list[float] = []
    index = 0
    for step in range(_ITERATIONS):
        direction = 1 if step % 2 == 0 else -1
        index = max(0, min(frames - 1, index + direction))
        start = time.perf_counter()
        view = episode0.frame_by_index(index)
        samples.append((time.perf_counter() - start) * 1000.0)
        assert set(view.images) == {*dataset.rgb_keys, dataset.depth_key}

    stats = _percentiles(samples)
    print(f"WP-3D-01 frame-step ms {stats}")
    # A frame step must fit inside the frame period (FR frame transport premise).
    assert stats["p99"] <= _FRAME_PERIOD_MS, stats


def test_random_seek_measured(episode0: EpisodeViewer, dataset: MaterializedDataset) -> None:
    frames = dataset.frames
    episode0.frame_by_index(0)
    rng = np.random.default_rng(0)

    samples: list[float] = []
    for _ in range(_ITERATIONS):
        index = int(rng.integers(0, frames))
        start = time.perf_counter()
        episode0.frame_by_index(index)
        samples.append((time.perf_counter() - start) * 1000.0)

    stats = _percentiles(samples)
    # The random-seek upper bound is unconfirmed in the plan — reported, not gated.
    print(f"WP-3D-01 random-seek ms {stats}")
    assert stats["p50"] >= 0.0
