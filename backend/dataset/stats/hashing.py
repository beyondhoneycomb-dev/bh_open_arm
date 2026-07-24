"""Content-hash a fitted statistics table for lineage and inference (WP-3D-03 ④).

The stats content hash is recorded in the lineage record and the checkpoint (`02b`
§8.1 WP-3D-04 consumes it), and a mismatch at inference — the normalization
statistics differing from the ones the checkpoint was trained under — is warned
(`02b` §8.2 WP-3D-03 ④). The digest is SHA-256 over a canonical serialization:
features and metrics in sorted order, every array cast to float64 and hashed with
its shape, so the same statistics produce the same digest on any platform a
checkpoint reaches.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Mapping

import numpy as np

from backend.dataset.stats.constants import STATS_HASH_ALGORITHM
from backend.dataset.stats.fit import DiagnosticStats, NormalizationStats

logger = logging.getLogger(__name__)

_CANONICAL_DTYPE = np.float64

# A fitted table, or a stats object carrying one.
StatsInput = NormalizationStats | DiagnosticStats | Mapping[str, Mapping[str, np.ndarray]]


def _table_of(stats: StatsInput) -> Mapping[str, Mapping[str, np.ndarray]]:
    """Return the per-feature table of a stats object, or the table itself."""
    if isinstance(stats, NormalizationStats | DiagnosticStats):
        return stats.per_feature
    return stats


def stats_content_hash(stats: StatsInput) -> str:
    """Compute the canonical content hash of a fitted statistics table.

    Args:
        stats: A fitted stats object, or a raw `feature -> metric -> array` table (as
            read back from a saved dataset).

    Returns:
        (str) The hex SHA-256 digest of the canonical serialization.
    """
    table = _table_of(stats)
    digest = hashlib.new(STATS_HASH_ALGORITHM)
    for feature in sorted(table):
        digest.update(feature.encode("utf-8"))
        metrics = table[feature]
        for metric in sorted(metrics):
            array = np.ascontiguousarray(np.asarray(metrics[metric], dtype=_CANONICAL_DTYPE))
            digest.update(metric.encode("utf-8"))
            digest.update(str(array.shape).encode("utf-8"))
            digest.update(array.tobytes())
    return digest.hexdigest()


def verify_stats_hash(recorded_hash: str, stats: StatsInput) -> bool:
    """Return whether a statistics table still hashes to a recorded digest.

    Args:
        recorded_hash: The stats hash stored in the lineage record / checkpoint.
        stats: The statistics to re-hash.

    Returns:
        (bool) True when the current hash equals the recorded one.
    """
    return stats_content_hash(stats) == recorded_hash


def warn_on_stats_hash_mismatch(recorded_hash: str, stats: StatsInput) -> bool:
    """Warn when inference statistics differ from the recorded training hash.

    Args:
        recorded_hash: The stats hash stored in the lineage record / checkpoint.
        stats: The statistics normalization would use at inference.

    Returns:
        (bool) True when the hashes match; False (after logging a warning) otherwise.
    """
    current = stats_content_hash(stats)
    if current == recorded_hash:
        return True
    logger.warning(
        "stats hash mismatch: checkpoint recorded %s but inference statistics hash %s; "
        "normalization differs from the training fit",
        recorded_hash,
        current,
    )
    return False
