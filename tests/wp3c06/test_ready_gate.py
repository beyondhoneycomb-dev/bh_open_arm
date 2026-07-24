"""The WP-3D-05 READY gate refuses a delete even when all four capture checks pass.

The interlock layers the capture-preservation checks on top of the committed
WP-3D-05 verifier; either one unmet refuses the delete. This proves the READY gate
is load-bearing on its own: a converted dataset that WP-3D-05 rules INVALID is not
deletable even though the raw capture was perfectly preserved (`02b` §7.2 WP-3C-06).
"""

from __future__ import annotations

import pytest

from backend.capture_interlock import (
    VERDICT_REFUSED,
    CaptureSource,
    SourceDeleteInterlock,
)
from backend.dataset.integrity import IntegrityError, ensure_training_ready
from tests.wp3c06 import faults
from tests.wp3c06.materialize import Fixture


def test_stats_hash_corruption_makes_dataset_invalid(pair: Fixture) -> None:
    """Sanity: the injected stats corruption is exactly what WP-3D-05 rules INVALID."""
    faults.inject_ready_invalid(pair)
    with pytest.raises(IntegrityError):
        ensure_training_ready(pair.converted_root)


def test_invalid_dataset_refuses_delete_though_capture_preserved(pair: Fixture) -> None:
    """A non-READY converted dataset refuses the delete while every capture check passes."""
    faults.inject_ready_invalid(pair)

    decision = SourceDeleteInterlock().decide(pair.raw_root, pair.converted_root)

    # The capture layer is intact — every episode preserved, all four checks passed.
    assert decision.all_preserved
    for episode in decision.episodes:
        assert episode.preserved, episode.reasons()

    # But READY failed, so the delete is refused.
    assert not decision.training_ready
    assert not decision.deletable
    assert decision.verdict == VERDICT_REFUSED


def test_invalid_dataset_delete_is_a_no_op_on_the_source(pair: Fixture) -> None:
    """delete_if_certified leaves the raw source intact when the dataset is not READY."""
    faults.inject_ready_invalid(pair)
    source = CaptureSource(pair.raw_root)

    outcome = SourceDeleteInterlock().delete_if_certified(pair.raw_root, pair.converted_root)

    assert not outcome.deleted
    assert source.exists()
    assert source.episode_indices() == tuple(range(pair.episodes))
