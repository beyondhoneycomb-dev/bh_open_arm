"""A faithful conversion is deletable, and the delete removes only the raw source.

The positive case the whole interlock rests on: when the converted dataset is READY
and every capture-preservation check passes, the raw source is DELETABLE and the
delete path removes it — and nothing else (`02b` §7.2 WP-3C-06).
"""

from __future__ import annotations

from backend.capture_interlock import (
    REQUIRED_CAPTURE_CHECKS,
    VERDICT_DELETABLE,
    CaptureSource,
    SourceDeleteInterlock,
)
from backend.dataset.integrity import ensure_training_ready
from tests.wp3c06.materialize import Fixture


def test_fixture_converted_dataset_is_training_ready(pair: Fixture) -> None:
    """The materialized converted dataset genuinely certifies READY via WP-3D-05."""
    report = ensure_training_ready(pair.converted_root)
    assert report.ready


def test_faithful_pair_all_checks_pass_and_is_deletable(pair: Fixture) -> None:
    """Every episode passes all four checks and the decision is DELETABLE."""
    decision = SourceDeleteInterlock().decide(pair.raw_root, pair.converted_root)

    assert decision.training_ready
    assert decision.verdict == VERDICT_DELETABLE
    assert decision.deletable
    assert decision.flagged_episodes == ()
    assert len(decision.episodes) == pair.episodes
    for episode in decision.episodes:
        assert episode.preserved, episode.reasons()
        assert episode.checks_ran == frozenset(REQUIRED_CAPTURE_CHECKS)


def test_delete_if_certified_removes_only_the_raw_source(pair: Fixture) -> None:
    """A DELETABLE decision deletes the raw source and leaves the converted dataset."""
    interlock = SourceDeleteInterlock()
    source = CaptureSource(pair.raw_root)
    assert source.exists()

    outcome = interlock.delete_if_certified(pair.raw_root, pair.converted_root)

    assert outcome.deleted
    assert outcome.flagged_episodes == ()
    assert not source.exists()
    # The converted dataset is untouched and still verifies READY.
    assert ensure_training_ready(pair.converted_root).ready
