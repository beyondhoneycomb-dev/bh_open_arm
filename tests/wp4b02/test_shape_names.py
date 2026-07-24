"""CG-4B-02a/b/d — shape and `names` compatibility (FR-TRN-062).

The checkpoint-side symmetry of the WP-4A-02 `names`-authority rule: a checkpoint and a
dataset are compatible only when their `observation.state` names match as an ORDERED
tuple. Width equality is not compatibility — the negative branch of CG-4B-02d.
"""

from __future__ import annotations

from backend.compat.checkpoint_dataset import (
    DeploymentIntent,
    IncompatibilityCode,
    check_compatibility,
)
from tests.wp4b02.support import (
    FULL_NAMES,
    POS_ONLY_NAMES,
    checkpoint_attachment,
    dataset_target,
)


def test_position_only_checkpoint_rejects_full_dataset() -> None:
    """CG-4B-02a: a 16-dim position-only checkpoint fed a 48-dim dataset does not train."""
    checkpoint = checkpoint_attachment(names=POS_ONLY_NAMES)
    dataset = dataset_target(names=FULL_NAMES)

    verdict = check_compatibility(checkpoint, dataset, DeploymentIntent.TRAINING)

    assert not verdict.allowed
    codes = {reason.code for reason in verdict.reasons}
    assert IncompatibilityCode.STATE_NAMES_MISMATCH in codes
    names_reason = next(
        r for r in verdict.reasons if r.code is IncompatibilityCode.STATE_NAMES_MISMATCH
    )
    assert names_reason.rule_id == "FR-TRN-062"


def test_full_checkpoint_rejects_position_only_dataset() -> None:
    """CG-4B-02b: the reverse — a 48-dim checkpoint fed a 16-dim dataset does not train."""
    checkpoint = checkpoint_attachment(names=FULL_NAMES)
    dataset = dataset_target(names=POS_ONLY_NAMES)

    verdict = check_compatibility(checkpoint, dataset, DeploymentIntent.TRAINING)

    assert not verdict.allowed
    assert any(r.code is IncompatibilityCode.STATE_NAMES_MISMATCH for r in verdict.reasons)


def test_same_width_reordered_names_is_blocked() -> None:
    """CG-4B-02d: identical width but a rotated `names` order is a block, not a pass."""
    reordered = list(FULL_NAMES)
    reordered[0], reordered[1] = reordered[1], reordered[0]

    checkpoint = checkpoint_attachment(names=FULL_NAMES)
    dataset = dataset_target(names=reordered)

    # A shape-only reader would pass this pairing: the widths are equal.
    assert len(checkpoint.state_names()) == len(dataset.state_names())

    verdict = check_compatibility(checkpoint, dataset, DeploymentIntent.TRAINING)

    assert not verdict.allowed
    names_reason = next(
        r for r in verdict.reasons if r.code is IncompatibilityCode.STATE_NAMES_MISMATCH
    )
    assert "diverge at index 0" in names_reason.detail


def test_matching_shape_and_names_is_allowed() -> None:
    """The positive control: identical names and action width train without a block."""
    checkpoint = checkpoint_attachment(names=FULL_NAMES)
    dataset = dataset_target(names=FULL_NAMES)

    verdict = check_compatibility(checkpoint, dataset, DeploymentIntent.TRAINING)

    assert verdict.allowed
    assert verdict.reasons == ()
