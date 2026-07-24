"""The stale-propagation hook for the deployment gate (`02c` §2.2 대가).

Blocking on the stats hash has a price the plan states plainly: recomputing a
dataset's statistics — a `q01`/`q99` augmentation (`FR-TRN-020`) or any re-fit —
changes its content hash, and every checkpoint trained under the OLD hash becomes
undeployable. This module makes that propagation explicit for a set of DEPLOYMENT
candidates, the consumer-side mirror of WP-4A-05's lineage-store stale marking
(`CG-4A-05d`): given the current statistics per dataset version, it derives which
checkpoints a stats change has made non-deployable.

Staleness is DERIVED, never stored: the only inputs are the checkpoint attachments and
the current statistics, and a checkpoint is stale exactly when its dataset's current
statistics no longer hash to the contract's recorded hash. The comparison reuses the
committed `contract_is_stale` (WP-4A-04, which defers to the one WP-3D-03
canonicalization), so there is no second staleness rule to drift from the maker's.
`DatasetKey` is reused from WP-4A-05 rather than re-declared.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from backend.compat.checkpoint_dataset.inputs import CheckpointAttachment
from backend.dataset.stats.hashing import StatsInput
from backend.training.lineage.stale import DatasetKey
from backend.training.normstats import contract_is_stale


def _dataset_key(checkpoint: CheckpointAttachment) -> DatasetKey:
    """The dataset-version key a checkpoint's current statistics are looked up by.

    Args:
        checkpoint: The checkpoint whose lineage identifies its dataset version.

    Returns:
        (DatasetKey) The `(repo_id, revision)` of the dataset the checkpoint trained on.
    """
    return DatasetKey(
        repo_id=checkpoint.lineage.dataset.repo_id,
        revision=checkpoint.lineage.dataset.revision,
    )


def is_deployment_stale(checkpoint: CheckpointAttachment, current_stats: StatsInput) -> bool:
    """Report whether a checkpoint has become undeployable under changed statistics.

    Wraps the WP-4A-04 `contract_is_stale`, so the verdict uses the one committed hash
    rule: a checkpoint is deployment-stale exactly when its dataset's current statistics
    no longer hash to the checkpoint's normalization contract.

    Args:
        checkpoint: The checkpoint whose recorded serving hash is the reference.
        current_stats: The dataset's statistics as they stand now.

    Returns:
        (bool) True when the current statistics have drifted from the recorded hash.
    """
    return contract_is_stale(checkpoint.normalization, current_stats)


def stale_deployments(
    checkpoints: Sequence[CheckpointAttachment],
    current_stats: Mapping[DatasetKey, StatsInput],
) -> tuple[CheckpointAttachment, ...]:
    """Return the checkpoints a stats recomputation has made non-deployable.

    A pure function of the attachments and the supplied current statistics: no flag is
    written, mirroring WP-4A-05's automatic marking. A checkpoint whose dataset version
    is absent from `current_stats` is not evaluated — its statistics are unknown, not
    assumed changed or unchanged.

    Args:
        checkpoints: The deployment candidates to test.
        current_stats: The current statistics per dataset version.

    Returns:
        (tuple[CheckpointAttachment, ...]) The stale checkpoints, in input order.
    """
    stale: list[CheckpointAttachment] = []
    for checkpoint in checkpoints:
        current = current_stats.get(_dataset_key(checkpoint))
        if current is None:
            continue
        if is_deployment_stale(checkpoint, current):
            stale.append(checkpoint)
    return tuple(stale)
