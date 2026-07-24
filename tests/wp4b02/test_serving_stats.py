"""CG-4B-02c — the serving stats-hash mismatch is a BLOCK, not a warning.

`FR-TRN-025` wins over `FR-DAT-032`: a one-bit change in the deployed dataset's
statistics blocks deployment with `OA-DAT-002`, because a different digest means a
different denormalization and thus a different physical joint command. The comparer
imports the committed `verify_stats_hash` — it compares, it never re-canonicalizes.
"""

from __future__ import annotations

import pytest

from backend.compat.checkpoint_dataset import (
    CheckpointDatasetMismatchError,
    DeploymentIntent,
    IncompatibilityCode,
    assert_deployable,
    check_compatibility,
)
from contracts.errors import codes
from tests.wp4b02.support import (
    FULL_NAMES,
    checkpoint_attachment,
    dataset_target,
    one_bit_changed_stats,
)


def test_one_bit_stats_change_blocks_deployment() -> None:
    """A serving dataset whose stats differ by one bit is blocked with OA-DAT-002."""
    checkpoint = checkpoint_attachment(names=FULL_NAMES)
    dataset = dataset_target(names=FULL_NAMES, stats_table=one_bit_changed_stats())

    verdict = check_compatibility(checkpoint, dataset, DeploymentIntent.SERVING)

    assert not verdict.allowed
    stats_reason = next(
        r for r in verdict.reasons if r.code is IncompatibilityCode.STATS_HASH_MISMATCH
    )
    assert stats_reason.rule_id == "FR-TRN-025"
    assert "OA-DAT-002" in stats_reason.detail


def test_stats_block_raises_oa_dat_002() -> None:
    """The enforcement site raises OA-DAT-002, so serving cannot proceed past the block."""
    checkpoint = checkpoint_attachment(names=FULL_NAMES)
    dataset = dataset_target(names=FULL_NAMES, stats_table=one_bit_changed_stats())

    with pytest.raises(CheckpointDatasetMismatchError) as caught:
        assert_deployable(checkpoint, dataset)

    assert caught.value.code == codes.OA_DAT_002


def test_matching_stats_clears_deployment() -> None:
    """The positive control: identical statistics serve without a block."""
    checkpoint = checkpoint_attachment(names=FULL_NAMES)
    dataset = dataset_target(names=FULL_NAMES)  # committed fit == checkpoint's recorded hash

    verdict = check_compatibility(checkpoint, dataset, DeploymentIntent.SERVING)

    assert verdict.allowed
    assert_deployable(checkpoint, dataset)  # does not raise


def test_stats_mismatch_is_not_checked_under_training_intent() -> None:
    """FR-TRN-025 is a SERVING block; a stats drift alone does not stop TRAINING.

    The intent distinction is load-bearing: the deployment block belongs to serving, and
    a shape-compatible pair with drifted stats is a training candidate, not a deployable.
    """
    checkpoint = checkpoint_attachment(names=FULL_NAMES)
    dataset = dataset_target(names=FULL_NAMES, stats_table=one_bit_changed_stats())

    verdict = check_compatibility(checkpoint, dataset, DeploymentIntent.TRAINING)

    assert verdict.allowed
    assert all(r.code is not IncompatibilityCode.STATS_HASH_MISMATCH for r in verdict.reasons)
