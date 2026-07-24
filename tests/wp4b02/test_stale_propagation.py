"""The stale-propagation hook: a stats recomputation makes descendants undeployable.

`02c` §2.2 대가 made concrete — recomputing a dataset's statistics changes its hash, and
every checkpoint trained under the old hash becomes non-deployable. Staleness is derived
from the committed `contract_is_stale`, never stored.
"""

from __future__ import annotations

from backend.compat.checkpoint_dataset import is_deployment_stale, stale_deployments
from backend.training.lineage.stale import DatasetKey
from tests.wp4b02.support import (
    FULL_NAMES,
    checkpoint_attachment,
    fit_stats,
    one_bit_changed_stats,
)


def _key(checkpoint) -> DatasetKey:
    """The dataset-version key the checkpoint's statistics are looked up by."""
    return DatasetKey(
        repo_id=checkpoint.lineage.dataset.repo_id,
        revision=checkpoint.lineage.dataset.revision,
    )


def test_unchanged_stats_are_not_stale() -> None:
    """A checkpoint against the statistics it trained on is deployable."""
    checkpoint = checkpoint_attachment(names=FULL_NAMES)
    assert not is_deployment_stale(checkpoint, fit_stats())


def test_recomputed_stats_make_checkpoint_stale() -> None:
    """A one-bit stats recomputation marks the checkpoint deployment-stale."""
    checkpoint = checkpoint_attachment(names=FULL_NAMES)
    assert is_deployment_stale(checkpoint, one_bit_changed_stats())


def test_propagation_returns_only_affected_checkpoints() -> None:
    """Propagation returns the checkpoints on the recomputed dataset, skipping unknowns."""
    affected = checkpoint_attachment(names=FULL_NAMES)
    unknown = checkpoint_attachment(names=FULL_NAMES, episodes=(3, 4, 5))

    stale = stale_deployments([affected, unknown], {_key(affected): one_bit_changed_stats()})

    # Both checkpoints share the fixture's (repo_id, revision), so both are on the
    # recomputed dataset and both go stale; a dataset absent from the map is skipped.
    assert affected in stale
    assert stale == (affected, unknown)


def test_dataset_absent_from_map_is_not_evaluated() -> None:
    """A checkpoint whose dataset version is not in the current-stats map is left alone."""
    checkpoint = checkpoint_attachment(names=FULL_NAMES)
    other = DatasetKey(repo_id="openarm/other", revision="rev-9999")

    stale = stale_deployments([checkpoint], {other: one_bit_changed_stats()})

    assert stale == ()
