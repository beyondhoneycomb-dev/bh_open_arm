"""The composition is real: element (a) reuses WP-4A-04's stats hash, (h) WP-4A-03's.

`02c` §1.5 forbids forking upstream. These tests pin the reuse: the recorded
`stats_hash` is the committed `NormalizationContract` hash bit-for-bit, and element
(h) round-trips as WP-4A-03's own `DegenerateDecision`, not a re-declared shape.
"""

from __future__ import annotations

from backend.training.degenerate import DegenerateChoice, DegenerateDecision
from backend.training.lineage import CheckpointId, TrainingLineageStore
from backend.training.normstats import build_normalization_contract, contract_is_stale
from tests.wp4a05.support import fit_stats, fixture_contract, fixture_record, sample_decision

_CONTENT_HASH = "content-hash-fixture"


def test_dataset_stats_hash_is_the_committed_contract_hash() -> None:
    """Element (a) `stats_hash` equals WP-4A-04's `stats_content_hash`, not a re-hash."""
    contract = fixture_contract()
    record = fixture_record(contract=contract)
    assert record.dataset.stats_hash == contract.stats_hash
    # And it verifies against the committed contract for the same statistics.
    rebuilt = build_normalization_contract(fit_stats())
    assert record.dataset.stats_hash == rebuilt.stats_hash
    assert contract_is_stale(rebuilt, fit_stats()) is False


def test_element_h_round_trips_as_wp4a03_decisions(tmp_path) -> None:
    """Element (h) reads back as WP-4A-03 `DegenerateDecision` objects unchanged."""
    decision = sample_decision()
    checkpoint = CheckpointId("/runs/a", 1000)
    with TrainingLineageStore(tmp_path) as store:
        store.record(fixture_record(degenerate_decisions=[decision]), checkpoint, _CONTENT_HASH)
        restored = store.snapshot_of(checkpoint)
    assert restored is not None
    assert len(restored.degenerate_decisions) == 1
    read = restored.degenerate_decisions[0]
    assert isinstance(read, DegenerateDecision)
    assert read.choice is DegenerateChoice.EXCLUDE
    assert read.finding.channel_name == decision.finding.channel_name
    assert read.finding.component == decision.finding.component
    assert read.finding.norm_mode == decision.finding.norm_mode


def test_empty_element_h_round_trips_as_empty(tmp_path) -> None:
    """A clean run records element (h) as an empty tuple and reads it back empty."""
    checkpoint = CheckpointId("/runs/a", 1000)
    with TrainingLineageStore(tmp_path) as store:
        store.record(fixture_record(degenerate_decisions=[]), checkpoint, _CONTENT_HASH)
        restored = store.snapshot_of(checkpoint)
    assert restored is not None
    assert restored.degenerate_decisions == ()
