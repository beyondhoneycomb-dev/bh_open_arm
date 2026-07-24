"""WP-3D-03 ⑤ — the fit streams: peak memory does not grow proportionally with episodes.

`02b` §8.2 WP-3D-03 ⑤: peak RSS must grow within 10% from 10 to 100 episodes;
proportional growth means streaming is not implemented and is a regression. This is
proven three ways: the fit holds one episode alive at a time, its retained state is
O(dim) rather than O(episodes), and the process peak RSS measured in a child process
stays essentially flat between a 10- and a 100-episode fit. Incremental folding is
also shown to be numerically identical to aggregating the whole list at once.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

import backend.dataset.stats as stats
from tests.wp3d03 import support

_REPO_ROOT = Path(__file__).resolve().parents[2]

# The RSS-marginal floor (KB) absorbed as measurement noise. A streaming fit adds
# roughly one episode's worth of memory regardless of episode count, so the 10-vs-100
# marginal difference sits far below this; a load-everything regression at this
# episode size would add ~90 MB and clear it decisively.
_RSS_NOISE_FLOOR_KB = 40_000

# Measure the fit's peak RSS above the post-import baseline for a 10- and a
# 100-episode fit, in a fresh interpreter, and print the two marginals as JSON. Each
# episode is ~1 MB, so a non-streaming fit would make the 100-episode marginal ~10x
# the 10-episode one, while a streaming fit keeps them equal.
_RSS_SCRIPT = """
import json, resource
import numpy as np
from backend.dataset.stats.fit import fit_normalization_stats

ACTION_DIM, STATE_DIM, FRAMES = 16, 48, 4000
FEATURES = {
    "action": {"dtype": "float32", "shape": (ACTION_DIM,)},
    "observation.state": {"dtype": "float32", "shape": (STATE_DIM,)},
}


def episodes(count):
    rng = np.random.default_rng(0)
    for _ in range(count):
        yield {
            "action": rng.standard_normal((FRAMES, ACTION_DIM)).astype("float32"),
            "observation.state": rng.standard_normal((FRAMES, STATE_DIM)).astype("float32"),
        }


baseline = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
marginals = {}
for count in (10, 100):
    fit_normalization_stats(episodes(count), FEATURES)
    marginals[str(count)] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss - baseline
print(json.dumps(marginals))
"""


def test_fit_holds_one_episode_at_a_time() -> None:
    """A streaming fit never holds more than one episode (two, with GC slack) alive."""
    feats = support.features()
    tracker = support.LiveEpisodeTracker()

    def generator(count: int):
        for index in range(count):
            yield tracker.wrap(support.episode(index))

    stats.fit_normalization_stats(generator(100), feats)

    assert tracker.max_live <= 2


def test_retained_state_is_independent_of_episode_count() -> None:
    """The fitted table is O(dim): its byte size is identical for 10 and 100 episodes."""
    feats = support.features()
    ten = stats.fit_normalization_stats(support.episode_generator(10), feats)
    hundred = stats.fit_normalization_stats(support.episode_generator(100), feats)

    def table_bytes(fitted: stats.NormalizationStats) -> int:
        return sum(
            np.asarray(value).nbytes
            for metrics in fitted.per_feature.values()
            for value in metrics.values()
        )

    assert ten.frame_count * 10 == hundred.frame_count
    assert table_bytes(ten) == table_bytes(hundred)


def test_incremental_fold_equals_batch_aggregate() -> None:
    """Streaming folds to the same table as aggregating every episode at once."""
    from lerobot.datasets.compute_stats import aggregate_stats, compute_episode_stats

    feats = support.features()
    episodes = [support.episode(index, frames=10) for index in range(5)]
    per_episode = [
        compute_episode_stats(dict(episode), dict(feats), quantile_list=list(stats.QUANTILE_LEVELS))
        for episode in episodes
    ]
    batch = aggregate_stats(per_episode)
    stream = stats.fit_normalization_stats(iter(episodes), feats)

    for feature in feats:
        for metric in stats.METRIC_KEYS:
            assert np.array_equal(
                np.asarray(batch[feature][metric]),
                np.asarray(stream.per_feature[feature][metric]),
            )


def test_peak_rss_growth_within_bound() -> None:
    """Measured peak RSS grows within 10% from a 10- to a 100-episode fit."""
    completed = subprocess.run(
        [sys.executable, "-c", _RSS_SCRIPT],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    marginals = json.loads(completed.stdout.strip().splitlines()[-1])
    ten = marginals["10"]
    hundred = marginals["100"]

    assert hundred <= ten * 1.10 + _RSS_NOISE_FLOOR_KB
