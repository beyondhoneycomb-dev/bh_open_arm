"""WP-3D-03 ④ — the stats content hash is stable, sensitive, and warns on mismatch.

`02b` §8.2 WP-3D-03 ④: the stats content hash is recorded in lineage/checkpoint and a
mismatch at inference is warned. The digest is deterministic for identical statistics,
changes when any value changes, and drives an inference-time warning when the
statistics differ from the recorded ones.
"""

from __future__ import annotations

import copy
import logging

import numpy as np

import backend.dataset.stats as stats
from contracts.recorder import ACTION_KEY
from tests.wp3d03 import support


def _fit() -> stats.NormalizationStats:
    """Fit a small deterministic normalization for the hash tests."""
    feats = support.features()
    return stats.fit_normalization_stats([support.episode(index) for index in range(3)], feats)


def test_hash_is_deterministic() -> None:
    """Identical statistics hash to the same digest."""
    assert stats.stats_content_hash(_fit()) == stats.stats_content_hash(_fit())


def test_hash_accepts_a_raw_table() -> None:
    """A raw `feature -> metric -> array` table (read from disk) hashes to the same digest."""
    fitted = _fit()
    assert stats.stats_content_hash(fitted) == stats.stats_content_hash(fitted.per_feature)


def test_hash_changes_when_a_value_changes() -> None:
    """A one-value perturbation changes the digest — the hash is content-sensitive."""
    fitted = _fit()
    baseline = stats.stats_content_hash(fitted)

    perturbed = copy.deepcopy(fitted.per_feature)
    perturbed[ACTION_KEY]["mean"] = np.asarray(perturbed[ACTION_KEY]["mean"], dtype=np.float64)
    perturbed[ACTION_KEY]["mean"][0] += 1.0

    assert stats.stats_content_hash(perturbed) != baseline


def test_verify_stats_hash_roundtrip() -> None:
    """A recorded hash verifies against its own statistics and fails a wrong one."""
    fitted = _fit()
    recorded = stats.stats_content_hash(fitted)

    assert stats.verify_stats_hash(recorded, fitted)
    assert not stats.verify_stats_hash("0" * 64, fitted)


def test_warn_on_mismatch_only_when_it_differs(caplog: object) -> None:
    """A matching hash is silent; a mismatch returns False and warns."""
    fitted = _fit()
    recorded = stats.stats_content_hash(fitted)

    with caplog.at_level(logging.WARNING, logger="backend.dataset.stats.hashing"):  # type: ignore[attr-defined]
        assert stats.warn_on_stats_hash_mismatch(recorded, fitted)
    assert not caplog.records  # type: ignore[attr-defined]

    with caplog.at_level(logging.WARNING, logger="backend.dataset.stats.hashing"):  # type: ignore[attr-defined]
        assert not stats.warn_on_stats_hash_mismatch("0" * 64, fitted)
    assert any(record.levelno == logging.WARNING for record in caplog.records)  # type: ignore[attr-defined]
