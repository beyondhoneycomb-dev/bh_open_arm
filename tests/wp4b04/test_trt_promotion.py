"""CG-4B-04c: a TRT engine below the 0.99 cosine gate is refused promotion (`FR-INF-032`).

The verify step of the TRT pipeline (export -> build -> verify -> benchmark) is a hard
gate: cosine >= 0.99 promotes, below refuses. A refused engine is a different model, so
the refusal must be unambiguous and carry the shortfall in its reason.
"""

from __future__ import annotations

from backend.compat.deploy_matrix.trt_promotion import (
    COSINE_PROMOTION_THRESHOLD,
    trt_promotion_verdict,
)


def test_threshold_is_099() -> None:
    """The FR-INF-032 accuracy gate is exactly 0.99."""
    assert COSINE_PROMOTION_THRESHOLD == 0.99


def test_at_or_above_threshold_promotes() -> None:
    """Cosine at or above 0.99 promotes the engine with no reason to report."""
    for cosine in (0.99, 0.995, 1.0):
        verdict = trt_promotion_verdict(cosine)
        assert verdict.promoted is True
        assert verdict.reason == ""


def test_below_threshold_refuses_promotion() -> None:
    """Cosine below 0.99 refuses promotion and names the shortfall."""
    verdict = trt_promotion_verdict(0.98)
    assert verdict.promoted is False
    assert "0.98" in verdict.reason
    assert "FR-INF-032" in verdict.reason


def test_just_below_threshold_still_refuses() -> None:
    """The boundary is strict: 0.9899 is below the gate and refused."""
    assert trt_promotion_verdict(0.9899).promoted is False
