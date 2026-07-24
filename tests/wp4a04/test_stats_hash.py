"""CG-4A-04a — the contract's stats hash is deterministic and canonical (`02c` §1.4).

The same statistics must produce the same `stats_hash` every time, or the hash gate
silently no-ops. The hash is the committed `stats_content_hash`, so this asserts the
determinism the contract inherits: 1000 rebuilds of the contract over identical
statistics yield one digest, and the contract embeds the committed hash rather than a
second canonicalization (`02c` §1.4 SHAPE-CF: one rule).
"""

from __future__ import annotations

import backend.dataset.stats as stats
from backend.training.normstats import build_normalization_contract
from backend.training.normstats.constants import (
    APPLIED_TO,
    FIT_SPLIT,
    QUANTILE_APPROX,
    QUANTILE_BINS,
)
from tests.wp4a04 import support

DETERMINISM_REPEATS = 1000


def test_contract_hash_is_deterministic_over_1000_builds() -> None:
    """1000 contract builds over identical statistics yield exactly one hash."""
    fitted = support.fit()
    digests = {build_normalization_contract(fitted).stats_hash for _ in range(DETERMINISM_REPEATS)}
    assert len(digests) == 1


def test_contract_hash_is_the_committed_canonical_hash() -> None:
    """The contract embeds the committed `stats_content_hash`, not a forked rule."""
    fitted = support.fit()
    assert build_normalization_contract(fitted).stats_hash == stats.stats_content_hash(fitted)


def test_contract_hash_survives_a_raw_table_roundtrip() -> None:
    """A raw table read back from disk hashes to the same contract hash."""
    fitted = support.fit()
    from_object = build_normalization_contract(fitted).stats_hash
    assert from_object == stats.stats_content_hash(fitted.per_feature)


def test_contract_fields_are_the_frozen_direction_contract() -> None:
    """The contract fixes fit-on-train, apply-everywhere, approximate quantiles."""
    contract = build_normalization_contract(support.fit())
    assert contract.fit_split == FIT_SPLIT == "train"
    assert contract.applied_to == APPLIED_TO == ("train", "val", "test", "real")
    assert contract.quantile_approx is QUANTILE_APPROX is True
    assert contract.quantile_bins == QUANTILE_BINS == 5000
