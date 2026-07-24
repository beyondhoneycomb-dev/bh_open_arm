"""The checkpoint<->dataset verdict, its reasons, and the OA-DAT-002 block error.

`02c` §2.2 fixes the shape of this gate's output: a `CompatibilityCheck(checkpoint,
dataset)` returns a verdict whose every block names the requirement it enforces, and
a stats-hash mismatch on the serving side is a BLOCK — not the `FR-DAT-032` inference
warning. The plan resolves the two requirements' disagreement in favour of the
stronger one (`FR-TRN-025` blocks deployment, `FR-DAT-032` merely warns): different
statistics denormalize to a different physical quantity, so serving under them emits
joint commands in the wrong units. `OA-DAT-002` is the block's error code (registry
message: "checkpoint-dataset mismatch", `14` §2.10), escalated here from a `W`-level
inference warning to a hard deployment block.

These are pure carriers with no comparison logic: the comparer (`gate`) fills them.
The block error is minted only from a blocked verdict, so a caller cannot fabricate an
`OA-DAT-002` block that skipped the comparison.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from contracts.errors import OaError, codes


class DeploymentIntent(StrEnum):
    """Why a checkpoint is being paired with a dataset — it selects which rules apply.

    `TRAINING` is fine-tuning or resuming (`FR-TRN-062`): the checkpoint's
    `input_features`/`output_features` shape must match the dataset's
    `observation.state`/`action`, judged by `names`. `SERVING` is deployment
    (`FR-TRN-025`): it adds the normalization stats-hash equality block on top of the
    shape rules, because a served policy denormalizes with the deployed dataset's
    statistics and a mismatch ships the wrong physical quantity.
    """

    TRAINING = "TRAINING"
    SERVING = "SERVING"


class IncompatibilityCode(StrEnum):
    """The kind of checkpoint<->dataset incompatibility a reason records.

    `STATE_NAMES_MISMATCH` and `ACTION_SHAPE_MISMATCH` are the two halves of
    `FR-TRN-062` (input and output features). `STATS_HASH_MISMATCH` is the
    `FR-TRN-025` serving block (`OA-DAT-002`). `LINEAGE_CONTRACT_DISAGREE` is the
    `CG-4B-02e` internal-consistency defect — the checkpoint's own lineage and
    normalization contract report different stats hashes, so the checkpoint cannot be
    trusted at all. `POLICY_INCOMPATIBLE` folds a WP-4B-01 matrix block (e.g. a 48-dim
    dataset against a 32-capped policy family the checkpoint was trained as).
    """

    STATE_NAMES_MISMATCH = "STATE_NAMES_MISMATCH"
    ACTION_SHAPE_MISMATCH = "ACTION_SHAPE_MISMATCH"
    STATS_HASH_MISMATCH = "STATS_HASH_MISMATCH"
    LINEAGE_CONTRACT_DISAGREE = "LINEAGE_CONTRACT_DISAGREE"
    POLICY_INCOMPATIBLE = "POLICY_INCOMPATIBLE"


@dataclass(frozen=True)
class IncompatibilityReason:
    """One reason a checkpoint and dataset are incompatible, with its requirement id.

    Attributes:
        code: The kind of incompatibility.
        rule_id: The requirement the block enforces — `FR-TRN-062` for a shape/names
            block, `FR-TRN-025` for the serving stats-hash block, `CG-4B-02e` for the
            lineage/contract disagreement, or the folded WP-4B-01 rule id for a policy
            block.
        checkpoint: The value observed on the checkpoint side, rendered for display.
        dataset: The value observed on the dataset side, rendered for display.
        detail: The operator-facing sentence explaining the block.
    """

    code: IncompatibilityCode
    rule_id: str
    checkpoint: str
    dataset: str
    detail: str


@dataclass(frozen=True)
class CheckpointDatasetVerdict:
    """The verdict of one `CompatibilityCheck(checkpoint, dataset)` under an intent.

    `allowed` is true only when no reason applies. The gate's job is to BLOCK: a
    permissive verdict on a position-only checkpoint fed a 48-dim dataset would let
    `lerobot-train` start and `max_state_dim` truncate silently, and a permissive
    verdict on a stats-drifted serving pair would ship joint commands in the wrong
    units. So a blocked verdict is a hard stop, not advice.

    Attributes:
        intent: The intent the check ran under (which rules applied).
        allowed: True only when `reasons` is empty.
        reasons: Every applicable block, one per violated rule; empty when compatible.
    """

    intent: DeploymentIntent
    allowed: bool
    reasons: tuple[IncompatibilityReason, ...]

    def raise_if_blocked(self) -> None:
        """Raise `CheckpointDatasetMismatchError` when the verdict is not allowed.

        The training gate (`CG-4B-02a`/`b`) reads `allowed` to decide whether to start;
        the serving gate (`CG-4B-02c`) uses this to make "no deployment past a mismatch"
        enforceable rather than advisory. A permitted verdict returns silently.

        Raises:
            CheckpointDatasetMismatchError: When `allowed` is false (`OA-DAT-002`).
        """
        if self.allowed:
            return
        raise CheckpointDatasetMismatchError(self)


class CheckpointDatasetMismatchError(OaError):
    """Deployment or training blocked: a checkpoint and dataset are incompatible.

    Carries the canonical `OA-DAT-002` code (`14` §2.10), whose registry message is
    exactly "checkpoint-dataset mismatch". `FR-TRN-025` escalates the serving stats
    case from the `FR-DAT-032` `W`-level warning to this block; a shape/names mismatch
    (`FR-TRN-062`) is the same code because it is the same class of failure — the
    checkpoint and the dataset do not describe the same physical vector.
    """

    def __init__(self, verdict: CheckpointDatasetVerdict) -> None:
        """Build the block error from the verdict that refused the pairing.

        Args:
            verdict: The blocked verdict; its reasons are attached for an operator.
        """
        super().__init__(codes.OA_DAT_002)
        self.verdict = verdict
