"""CG-4A-04b — a one-bit stats change makes every old-hash checkpoint stale (`02c` §1.4).

The stats hash is one of the `§0.4` stale axes: a checkpoint's contract records the
hash it was trained under, so when the statistics change by even one value the new hash
no longer matches the recorded one, and every checkpoint on the old hash is
automatically stale. This is not a defect but the definition — a policy trained on
different statistics is a different policy.
"""

from __future__ import annotations

import copy

import numpy as np

from backend.training.normstats import build_normalization_contract, contract_is_stale
from contracts.recorder import ACTION_KEY
from tests.wp4a04 import support


def test_a_matching_statistic_is_not_stale() -> None:
    """A checkpoint's contract is fresh against the exact statistics it was built on."""
    fitted = support.fit()
    contract = build_normalization_contract(fitted)
    assert not contract_is_stale(contract, fitted)


def test_a_one_bit_change_makes_the_checkpoint_stale() -> None:
    """Perturbing a single statistic value strands the old contract as stale."""
    fitted = support.fit()
    contract = build_normalization_contract(fitted)

    perturbed = copy.deepcopy(fitted.per_feature)
    perturbed[ACTION_KEY]["mean"] = np.asarray(perturbed[ACTION_KEY]["mean"], dtype=np.float64)
    perturbed[ACTION_KEY]["mean"][0] += 1.0

    assert contract_is_stale(contract, perturbed)


def test_a_different_hash_is_a_different_contract() -> None:
    """Changed statistics yield a different `stats_hash` — a different, stale contract."""
    fitted = support.fit()
    old_contract = build_normalization_contract(fitted)

    perturbed = copy.deepcopy(fitted.per_feature)
    perturbed[ACTION_KEY]["std"] = np.asarray(perturbed[ACTION_KEY]["std"], dtype=np.float64)
    perturbed[ACTION_KEY]["std"][0] += 1e-9
    new_contract = build_normalization_contract(
        type(fitted)(per_feature=perturbed, episode_count=1, frame_count=1)
    )

    assert new_contract.stats_hash != old_contract.stats_hash
