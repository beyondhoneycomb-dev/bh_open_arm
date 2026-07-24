"""CG-4B-02e — a compat-passing combo's stats hash agrees in lineage and checkpoint.

Element (a) of the WP-4A-05 lineage and the WP-4A-04 normalization contract are two
independent sources of the training stats hash; a trustworthy checkpoint reports them
equal (the committed recorder wires both from the one contract). The comparer verifies
this actively — a checkpoint whose two sources disagree is blocked.
"""

from __future__ import annotations

import dataclasses

from backend.compat.checkpoint_dataset import (
    DeploymentIntent,
    IncompatibilityCode,
    check_compatibility,
)
from backend.training.normstats import NormalizationContract
from tests.wp4b02.support import FULL_NAMES, checkpoint_attachment, dataset_target


def test_passing_combo_stats_hash_identical_in_lineage_and_contract() -> None:
    """CG-4B-02e: for a compatible pairing the lineage and contract hashes are equal."""
    checkpoint = checkpoint_attachment(names=FULL_NAMES)
    dataset = dataset_target(names=FULL_NAMES)

    verdict = check_compatibility(checkpoint, dataset, DeploymentIntent.SERVING)

    assert verdict.allowed
    assert checkpoint.lineage_stats_hash() == checkpoint.contract_stats_hash()
    assert all(r.code is not IncompatibilityCode.LINEAGE_CONTRACT_DISAGREE for r in verdict.reasons)


def test_internally_inconsistent_checkpoint_is_blocked() -> None:
    """A checkpoint whose lineage and contract report different hashes is refused.

    Proves the consistency check is not vacuous: splitting the two sources blocks the
    pairing even when the dataset itself matches the lineage.
    """
    checkpoint = checkpoint_attachment(names=FULL_NAMES)
    inconsistent = dataclasses.replace(
        checkpoint, normalization=NormalizationContract(stats_hash="0" * 64)
    )
    dataset = dataset_target(names=FULL_NAMES)

    verdict = check_compatibility(inconsistent, dataset, DeploymentIntent.TRAINING)

    assert not verdict.allowed
    assert any(r.code is IncompatibilityCode.LINEAGE_CONTRACT_DISAGREE for r in verdict.reasons)
