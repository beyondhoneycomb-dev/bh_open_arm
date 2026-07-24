"""The checkpoint<->dataset compatibility comparer (`02c` §2.2, WP-4B-02).

This is the COMPARER half of the stats-hash contract: WP-4A-04 (`backend.training.
normstats`) MAKES the hash and WP-3D-03 (`backend.dataset.stats`) owns the one
canonicalization; this module only COMPARES, importing `verify_stats_hash` rather than
re-canonicalizing. Keeping maker and comparer in separate files is deliberate — a
single canonicalization owned upstream means a stats change reliably changes the
digest here, and there is no second rule to drift from it.

The check has four independent blocks, gathered into one verdict:

- state `names` (`FR-TRN-062`): compared as an ORDERED tuple, never by width — a
  position-only checkpoint fed a pos+vel+torque dataset (or the reverse) differs in
  its names, and a same-width dataset with a rotated name order differs in order.
  Shape-equality is not compatibility (`CG-4B-02d`); this is the checkpoint-side
  symmetry of the WP-4A-02 `FR-TRN-061` rule.
- action width (`FR-TRN-062`): the output-features half.
- lineage/contract agreement (`CG-4B-02e`): the checkpoint's element (a) stats hash and
  its normalization contract's stats hash are two independent sources that a valid
  checkpoint reports equal; a disagreement is an internal defect that blocks any use.
- serving stats hash (`FR-TRN-025`): under `SERVING` intent only, the dataset's live
  statistics must re-hash to the checkpoint's recorded hash. A mismatch is a BLOCK, not
  the `FR-DAT-032` warning — different statistics denormalize to a different physical
  quantity (`OA-DAT-002`).

A fifth block is optional: when a WP-4B-01 matrix and the checkpoint's `policy_id` are
supplied, the dataset is evaluated against that policy family and any structural block
(e.g. bimanual 48 against a 32-capped family) folds in. The matrix is consulted, never
restated: this module reads its verdict.
"""

from __future__ import annotations

from backend.compat.checkpoint_dataset.inputs import CheckpointAttachment, DatasetTarget
from backend.compat.checkpoint_dataset.verdict import (
    CheckpointDatasetVerdict,
    DeploymentIntent,
    IncompatibilityCode,
    IncompatibilityReason,
)
from backend.compat.policy_matrix import CompatibilityMatrix
from backend.dataset.stats import verify_stats_hash
from backend.training.projection import ProjectionKind

# The requirements each block enforces, named rather than inlined (constants rule).
RULE_SHAPE = "FR-TRN-062"
RULE_SERVING_STATS = "FR-TRN-025"
RULE_LINEAGE_CONSISTENCY = "CG-4B-02e"

# The registry error code the serving stats block escalates to a deployment BLOCK
# (`14` §2.10); named here so the block detail can cite it without a bare literal.
STATS_BLOCK_CODE = "OA-DAT-002"

# The checkpoint<->dataset check consumes the dataset as recorded — no projection is
# applied to the candidate, so the policy axis is evaluated at FULL width.
_CANDIDATE_PROJECTION = ProjectionKind.FULL


def check_compatibility(
    checkpoint: CheckpointAttachment,
    dataset: DatasetTarget,
    intent: DeploymentIntent,
    matrix: CompatibilityMatrix | None = None,
) -> CheckpointDatasetVerdict:
    """Compare a checkpoint and a dataset and return every block that applies.

    This is the `CompatibilityCheck(checkpoint, dataset) -> Verdict` of `02c` §2.2. The
    state-names, action-width and lineage/contract blocks apply under both intents; the
    serving stats-hash block applies only under `SERVING`; the policy block applies only
    when `matrix` and `checkpoint.policy_id` are both present.

    Args:
        checkpoint: The checkpoint's immutable attachment.
        dataset: The candidate dataset (observation config plus live statistics).
        intent: `TRAINING` (fine-tune/resume) or `SERVING` (deployment).
        matrix: An optional WP-4B-01 matrix; when supplied with a `policy_id`, the
            dataset is also evaluated against the checkpoint's policy family.

    Returns:
        (CheckpointDatasetVerdict) The verdict; `allowed` is false when any block
            applies.
    """
    reasons: list[IncompatibilityReason] = []

    names_reason = _compare_state_names(checkpoint.state_names(), dataset.state_names())
    if names_reason is not None:
        reasons.append(names_reason)

    if checkpoint.action_dim() != dataset.action_dim():
        reasons.append(
            IncompatibilityReason(
                code=IncompatibilityCode.ACTION_SHAPE_MISMATCH,
                rule_id=RULE_SHAPE,
                checkpoint=str(checkpoint.action_dim()),
                dataset=str(dataset.action_dim()),
                detail=(
                    f"checkpoint output_features width {checkpoint.action_dim()} != dataset "
                    f"action width {dataset.action_dim()} ({RULE_SHAPE})"
                ),
            )
        )

    consistency_reason = _check_lineage_contract_agreement(checkpoint)
    if consistency_reason is not None:
        reasons.append(consistency_reason)

    if intent is DeploymentIntent.SERVING:
        stats_reason = _check_serving_stats(checkpoint, dataset)
        if stats_reason is not None:
            reasons.append(stats_reason)

    if matrix is not None and checkpoint.policy_id is not None:
        policy_reason = _check_policy(checkpoint.policy_id, dataset, matrix)
        if policy_reason is not None:
            reasons.append(policy_reason)

    return CheckpointDatasetVerdict(intent=intent, allowed=not reasons, reasons=tuple(reasons))


def assert_deployable(
    checkpoint: CheckpointAttachment,
    dataset: DatasetTarget,
    matrix: CompatibilityMatrix | None = None,
) -> None:
    """Run the `SERVING` check and raise unless the pairing is fully compatible.

    The single enforcement site for "no deployment past a checkpoint-dataset mismatch"
    (`FR-TRN-025`): it raises `CheckpointDatasetMismatchError` (`OA-DAT-002`) on any
    block, so a caller cannot proceed to serve past a stats or shape divergence.

    Args:
        checkpoint: The checkpoint's immutable attachment.
        dataset: The candidate serving dataset.
        matrix: An optional WP-4B-01 matrix for the policy axis.

    Raises:
        CheckpointDatasetMismatchError: When the serving pairing is not allowed.
    """
    check_compatibility(checkpoint, dataset, DeploymentIntent.SERVING, matrix).raise_if_blocked()


def _compare_state_names(
    checkpoint_names: tuple[str, ...], dataset_names: tuple[str, ...]
) -> IncompatibilityReason | None:
    """Compare state channel names as an ordered tuple, locating the first divergence.

    A width difference and an order/content difference are both blocks (`FR-TRN-062`):
    the first catches a position-only checkpoint against a pos+vel+torque dataset, the
    second catches a same-width dataset whose names were rotated (`CG-4B-02d`). The
    detail names the first index that diverges so an operator sees which channel moved.

    Args:
        checkpoint_names: The checkpoint's trained state names.
        dataset_names: The dataset's declared state names.

    Returns:
        (IncompatibilityReason | None) The block, or None when the names match exactly.
    """
    if checkpoint_names == dataset_names:
        return None

    if len(checkpoint_names) != len(dataset_names):
        detail = (
            f"checkpoint input_features width {len(checkpoint_names)} != dataset "
            f"observation.state width {len(dataset_names)}; names are the authority, so a "
            f"position-only checkpoint fed a pos+vel+torque dataset (or the reverse) is "
            f"refused ({RULE_SHAPE})"
        )
    else:
        divergence = next(
            index
            for index in range(len(checkpoint_names))
            if checkpoint_names[index] != dataset_names[index]
        )
        detail = (
            f"observation.state names diverge at index {divergence}: checkpoint "
            f"{checkpoint_names[divergence]!r} != dataset {dataset_names[divergence]!r}; "
            f"equal width is not compatibility — build_dataset_frame indexes by names order "
            f"({RULE_SHAPE})"
        )
    return IncompatibilityReason(
        code=IncompatibilityCode.STATE_NAMES_MISMATCH,
        rule_id=RULE_SHAPE,
        checkpoint=",".join(checkpoint_names),
        dataset=",".join(dataset_names),
        detail=detail,
    )


def _check_lineage_contract_agreement(
    checkpoint: CheckpointAttachment,
) -> IncompatibilityReason | None:
    """Verify the checkpoint's two recorded stats hashes agree (`CG-4B-02e`).

    Element (a) of the lineage and the normalization contract are independent sources
    of the training stats hash; a compatible checkpoint reports them equal (the recorder
    wires both from the one contract). A disagreement means the attachment is internally
    inconsistent and cannot be trusted for either training or serving.

    Args:
        checkpoint: The checkpoint's immutable attachment.

    Returns:
        (IncompatibilityReason | None) The block, or None when the two hashes agree.
    """
    if checkpoint.lineage_stats_hash() == checkpoint.contract_stats_hash():
        return None
    return IncompatibilityReason(
        code=IncompatibilityCode.LINEAGE_CONTRACT_DISAGREE,
        rule_id=RULE_LINEAGE_CONSISTENCY,
        checkpoint=checkpoint.lineage_stats_hash(),
        dataset=checkpoint.contract_stats_hash(),
        detail=(
            "checkpoint lineage element (a) stats hash and normalization contract stats hash "
            f"disagree; the attachment is internally inconsistent ({RULE_LINEAGE_CONSISTENCY})"
        ),
    )


def _check_serving_stats(
    checkpoint: CheckpointAttachment, dataset: DatasetTarget
) -> IncompatibilityReason | None:
    """Block serving when the dataset's statistics no longer hash to the checkpoint's.

    Reuses the committed `verify_stats_hash` (WP-3D-03 canonicalization) rather than a
    warning: `FR-TRN-025` wins over `FR-DAT-032`, so a one-bit stats change is a hard
    deployment BLOCK (`OA-DAT-002`), because a different digest means a different
    denormalization and thus a different physical joint command.

    Args:
        checkpoint: The checkpoint whose recorded serving hash is the reference.
        dataset: The serving dataset whose live statistics are re-hashed.

    Returns:
        (IncompatibilityReason | None) The block, or None when the hashes match.
    """
    if verify_stats_hash(checkpoint.contract_stats_hash(), dataset.stats):
        return None
    return IncompatibilityReason(
        code=IncompatibilityCode.STATS_HASH_MISMATCH,
        rule_id=RULE_SERVING_STATS,
        checkpoint=checkpoint.contract_stats_hash(),
        dataset="<recomputed from dataset statistics>",
        detail=(
            "serving normalization statistics do not hash to the checkpoint's training hash; "
            f"deployment BLOCKED ({STATS_BLOCK_CODE}, {RULE_SERVING_STATS} wins over FR-DAT-032) "
            "— different statistics denormalize to a different physical quantity"
        ),
    )


def _check_policy(
    policy_id: str, dataset: DatasetTarget, matrix: CompatibilityMatrix
) -> IncompatibilityReason | None:
    """Fold a WP-4B-01 matrix block for the dataset against the checkpoint's policy.

    The checkpoint was trained as one policy family, and fine-tuning or resuming keeps
    it; a dataset that the matrix refuses for that family (e.g. bimanual 48 against a
    32-capped family) cannot be paired regardless of shape agreement. The matrix's own
    verdict is consumed — this module renders it, it does not re-derive the ceiling.

    Args:
        policy_id: The checkpoint's policy family.
        dataset: The candidate dataset, whose WP-4A-02 observation config the matrix
            reads.
        matrix: The WP-4B-01 compatibility matrix.

    Returns:
        (IncompatibilityReason | None) The block, or None when the family accepts the
            dataset (or the family is not one the matrix ranks).
    """
    if policy_id not in matrix.policies():
        return None
    verdict = matrix.evaluate(policy_id, dataset.observation, _CANDIDATE_PROJECTION)
    if verdict.allowed:
        return None
    first = verdict.blocking_reasons[0]
    return IncompatibilityReason(
        code=IncompatibilityCode.POLICY_INCOMPATIBLE,
        rule_id=first.rule_id,
        checkpoint=policy_id,
        dataset=str(first.observed),
        detail=(
            f"dataset is incompatible with the checkpoint's policy {policy_id!r}: {first.message}"
        ),
    )
