"""The WP-4B-01 matrix is genuinely consulted for the checkpoint's policy family.

The checkpoint was trained as one policy family, and a dataset that family cannot take
is incompatible regardless of shape agreement. The block is DRIVEN by the matrix, not a
local table: a 48-dim dataset blocks a 32-capped family (SmolVLA) but not the 132-capped
one (GR00T), and with no matrix supplied the policy axis is simply not evaluated.
"""

from __future__ import annotations

from backend.compat.checkpoint_dataset import (
    DeploymentIntent,
    IncompatibilityCode,
    check_compatibility,
)
from backend.compat.policy_matrix import build_matrix
from tests.wp4b02.support import FULL_NAMES, checkpoint_attachment, dataset_target


def test_full_dataset_blocks_a_capped_policy_family() -> None:
    """A 48-dim dataset against a SmolVLA (max_state_dim=32) checkpoint folds in a block."""
    checkpoint = checkpoint_attachment(names=FULL_NAMES, policy_id="smolvla")
    dataset = dataset_target(names=FULL_NAMES)

    verdict = check_compatibility(
        checkpoint, dataset, DeploymentIntent.TRAINING, matrix=build_matrix()
    )

    assert not verdict.allowed
    assert any(r.code is IncompatibilityCode.POLICY_INCOMPATIBLE for r in verdict.reasons)


def test_full_dataset_accepted_by_uncapped_policy_family() -> None:
    """The same 48-dim dataset against GR00T (132) folds in no policy block."""
    checkpoint = checkpoint_attachment(names=FULL_NAMES, policy_id="groot")
    dataset = dataset_target(names=FULL_NAMES)

    verdict = check_compatibility(
        checkpoint, dataset, DeploymentIntent.TRAINING, matrix=build_matrix()
    )

    assert verdict.allowed
    assert all(r.code is not IncompatibilityCode.POLICY_INCOMPATIBLE for r in verdict.reasons)


def test_policy_axis_is_skipped_without_a_matrix() -> None:
    """With no matrix supplied the policy axis is not evaluated; shape/names still rule."""
    checkpoint = checkpoint_attachment(names=FULL_NAMES, policy_id="smolvla")
    dataset = dataset_target(names=FULL_NAMES)

    verdict = check_compatibility(checkpoint, dataset, DeploymentIntent.TRAINING)

    assert verdict.allowed
    assert all(r.code is not IncompatibilityCode.POLICY_INCOMPATIBLE for r in verdict.reasons)
