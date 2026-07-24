"""CG-4A-04d — a serving/training hash mismatch BLOCKS deployment (`02c` §1.4).

`FR-TRN-025`: when the serving-side normalization statistics differ from the ones the
checkpoint was trained under, deployment is blocked with `OA-DAT-002` — not the
`FR-DAT-032` inference warning, which the committed `warn_on_stats_hash_mismatch`
already owns. The plan escalates because differing statistics denormalize a policy's
output into a different physical quantity. The block is a raise (no clearance is
minted), and the error carries the canonical `OA-DAT-002` code.
"""

from __future__ import annotations

import copy

import numpy as np
import pytest

import backend.dataset.stats as stats
from backend.training.normstats import (
    ServingDeploymentClearance,
    ServingHashMismatchError,
    build_normalization_contract,
    clear_for_serving,
)
from contracts.errors import codes
from contracts.recorder import ACTION_KEY
from tests.wp4a04 import support


def test_matching_serving_hash_mints_a_clearance() -> None:
    """Identical serving statistics clear deployment and mint a token."""
    fitted = support.fit()
    contract = build_normalization_contract(fitted)

    clearance = clear_for_serving(contract, fitted)
    assert isinstance(clearance, ServingDeploymentClearance)
    assert clearance.stats_hash == contract.stats_hash


def test_mismatched_serving_hash_blocks_with_oa_dat_002() -> None:
    """Differing serving statistics raise the block, carrying OA-DAT-002."""
    fitted = support.fit()
    contract = build_normalization_contract(fitted)

    serving = copy.deepcopy(fitted.per_feature)
    serving[ACTION_KEY]["mean"] = np.asarray(serving[ACTION_KEY]["mean"], dtype=np.float64)
    serving[ACTION_KEY]["mean"][0] += 1.0

    with pytest.raises(ServingHashMismatchError) as raised:
        clear_for_serving(contract, serving)

    assert raised.value.code == codes.OA_DAT_002 == "OA-DAT-002"
    assert raised.value.training_hash == contract.stats_hash
    assert raised.value.serving_hash == stats.stats_content_hash(serving)


def test_the_block_is_distinct_from_the_inference_warning() -> None:
    """The serving block raises where the committed FR-DAT-032 path only warns."""
    fitted = support.fit()
    contract = build_normalization_contract(fitted)

    serving = copy.deepcopy(fitted.per_feature)
    serving[ACTION_KEY]["std"] = np.asarray(serving[ACTION_KEY]["std"], dtype=np.float64)
    serving[ACTION_KEY]["std"][0] += 1.0

    # FR-DAT-032 (committed): mismatch returns False, does not raise.
    assert not stats.warn_on_stats_hash_mismatch(contract.stats_hash, serving)
    # FR-TRN-025 (this band): the same mismatch is a hard block.
    with pytest.raises(ServingHashMismatchError):
        clear_for_serving(contract, serving)
