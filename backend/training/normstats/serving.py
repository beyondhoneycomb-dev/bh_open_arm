"""The serving-side normalization hash gate — a BLOCK, not a warning (`02c` §1.4).

Two requirements share the condition "the statistics normalization would use differ
from the ones the checkpoint was trained under" but disagree on severity, and the
plan resolves the conflict:

- `FR-DAT-032` warns at inference (`OA-DAT-002`, severity W). That is the committed
  `backend.dataset.stats.warn_on_stats_hash_mismatch`, which logs and continues.
- `FR-TRN-025` BLOCKS deployment. `02c` §1.4 / §4B-02 / the `N-2` ledger entry escalate
  the same `OA-DAT-002` code to a block: if the serving statistics differ, the
  denormalization differs, and a policy output denormalized under different statistics
  is a DIFFERENT physical quantity — shipping it is emitting joint commands in the
  wrong units. So this gate raises rather than warns.

This module owns the BLOCK half; the committed module owns the WARN half. They do not
compete: they are two severities of one condition, and the plan assigns each its FR.

The block is a capability token, not a flag: a `ServingDeploymentClearance` is the
object a caller needs to consider a checkpoint deployable, and `clear_for_serving` is
its only mint site, minting one only past the hash-equality check. That single-mint
property makes "no deployment past a hash mismatch" a static property, mirroring the
WP-4A-03 training gate.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.dataset.stats import stats_content_hash
from backend.dataset.stats.hashing import StatsInput
from backend.training.normstats.contract import NormalizationContract
from contracts.errors import OaError, codes


class ServingHashMismatchError(OaError):
    """Deployment blocked: serving statistics hash differs from the training contract.

    Carries the canonical `OA-DAT-002` code (`14` §2.10) so the block and the
    `FR-DAT-032` inference warning name the same failure, and attaches both hashes so
    an operator can see which statistics diverged. `FR-TRN-025`: a mismatch is a block,
    not the `W`-severity warning `FR-DAT-032` would raise.
    """

    def __init__(self, training_hash: str, serving_hash: str) -> None:
        """Build the block error for a training/serving hash mismatch.

        Args:
            training_hash: The hash the checkpoint's contract was trained under.
            serving_hash: The hash of the statistics serving would normalize with.
        """
        super().__init__(codes.OA_DAT_002)
        self.training_hash = training_hash
        self.serving_hash = serving_hash


@dataclass(frozen=True)
class ServingDeploymentClearance:
    """Proof the serving statistics hash matched the checkpoint's training contract.

    A capability token: holding one means `clear_for_serving` confirmed the serving
    statistics denormalize exactly as the checkpoint was trained to expect. Minted
    ONLY by `clear_for_serving`, so a clearance cannot be fabricated to skip the check
    (`CG-4A-04d`).

    Attributes:
        stats_hash: The matched hash, identical on the training and serving sides.
    """

    stats_hash: str


def clear_for_serving(
    contract: NormalizationContract, serving_stats: StatsInput
) -> ServingDeploymentClearance:
    """Mint a deployment clearance iff the serving hash equals the training hash.

    This is the sole mint site of `ServingDeploymentClearance`. It raises rather than
    returns on a mismatch, so no branch yields a clearance past differing statistics
    (`FR-TRN-025` block). The serving hash is the committed `stats_content_hash` — the
    same canonical rule the contract was built under, so an equal digest means
    identical denormalization, not merely equal bytes on this platform.

    Args:
        contract: The checkpoint's normalization contract, carrying the training hash.
        serving_stats: The statistics serving would normalize with (a fitted object or
            a raw table read back from the deployed dataset).

    Returns:
        (ServingDeploymentClearance) The token, when the hashes match.

    Raises:
        ServingHashMismatchError: When the serving hash differs from the contract's
            training hash (`OA-DAT-002`).
    """
    serving_hash = stats_content_hash(serving_stats)
    if serving_hash != contract.stats_hash:
        raise ServingHashMismatchError(training_hash=contract.stats_hash, serving_hash=serving_hash)
    return ServingDeploymentClearance(stats_hash=serving_hash)
