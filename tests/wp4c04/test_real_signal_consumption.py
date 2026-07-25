"""The engine consumes committed WP-4A-08 signals, and thresholds carry no default."""

from __future__ import annotations

import pytest

from backend.eval.taxonomy import (
    CorrelationEngine,
    EpisodeSignals,
    FailureTag,
    TaxonomyThresholds,
    placeholder_taxonomy_thresholds,
)
from backend.inference.runaway import FaultKind, InferencePhase
from tests.wp4c04.support import runaway_clamp_detector


def test_from_detector_reads_the_committed_terminal_state() -> None:
    """A real runaway drive, read via from_detector, yields both RUNAWAY and OUT_OF_BOUNDS.

    The detector faulted on CLIP_RATIO while every tick was a joint-limit clamp, so its
    committed terminal state (fault_kind + dual log) drives two auto-derived tags — no
    hand-forged signal anywhere.
    """
    detector = runaway_clamp_detector()
    assert detector.phase is InferencePhase.FAULT
    assert detector.fault_kind is FaultKind.RUNAWAY

    episode = EpisodeSignals.from_detector(
        detector,
        queue_exhaustion_ratio=0.0,
        disconnect_class=None,
        safety_stop_count=0,
        collision_count=0,
        torque_limit_hits=0,
    )
    tags = CorrelationEngine(placeholder_taxonomy_thresholds()).correlate(episode)
    assert FailureTag.POLICY_RUNAWAY in tags
    assert FailureTag.POLICY_OUT_OF_BOUNDS in tags


def test_thresholds_require_an_explicit_value() -> None:
    """TaxonomyThresholds has no default — a value must be supplied (SPINE §2-6 discipline)."""
    with pytest.raises(TypeError):
        TaxonomyThresholds()  # type: ignore[call-arg]


def test_placeholder_thresholds_are_usable_but_labelled() -> None:
    """The placeholder factory yields a usable, in-range ratio limit for the harness."""
    thresholds = placeholder_taxonomy_thresholds()
    assert 0.0 < thresholds.queue_exhaustion_ratio_max < 1.0
