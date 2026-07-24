"""The TensorRT engine-promotion accuracy gate (`FR-INF-032`, CG-4B-04c).

`FR-INF-032` fixes the TRT pipeline as ONNX export -> engine build -> cosine-similarity
accuracy verification -> benchmark, and makes the verify step a hard gate: an engine
whose output cosine similarity against the reference is below 0.99 must NOT be promoted
to a deployment target. Promotion is the act of blessing a built engine as servable, so
this gate stands between "built" and "servable" — a below-threshold engine is a
different model, and serving it silently would substitute one policy for another.

This module is the gate alone: given the measured cosine, it decides promotion. The
export/build/benchmark stages and the cosine measurement itself belong to the TRT
tooling; the number is the input, the verdict is the output.
"""

from __future__ import annotations

from dataclasses import dataclass

# `FR-INF-032` accuracy gate: the built engine's output must match the reference to at
# least this cosine similarity, or it is refused promotion. The source is the
# Isaac-GR00T deployment pipeline (`export -> build -> verify -> benchmark`).
COSINE_PROMOTION_THRESHOLD = 0.99


@dataclass(frozen=True)
class TrtPromotionVerdict:
    """The outcome of the `FR-INF-032` cosine accuracy gate.

    Attributes:
        cosine: The measured output cosine similarity against the reference.
        promoted: True only when `cosine` meets `COSINE_PROMOTION_THRESHOLD`.
        reason: Why the engine was refused, for the operator; empty when promoted.
    """

    cosine: float
    promoted: bool
    reason: str


def trt_promotion_verdict(cosine: float) -> TrtPromotionVerdict:
    """Decide whether a built TRT engine may be promoted, by its cosine (`FR-INF-032`).

    Args:
        cosine: The measured output cosine similarity against the reference model.

    Returns:
        (TrtPromotionVerdict) Promoted when `cosine >= COSINE_PROMOTION_THRESHOLD`,
            otherwise refused with the reason naming the shortfall.
    """
    if cosine >= COSINE_PROMOTION_THRESHOLD:
        return TrtPromotionVerdict(cosine=cosine, promoted=True, reason="")
    return TrtPromotionVerdict(
        cosine=cosine,
        promoted=False,
        reason=(
            f"TRT engine cosine {cosine} is below the {COSINE_PROMOTION_THRESHOLD} "
            "accuracy gate (FR-INF-032); promotion refused — a below-threshold engine is "
            "a different model"
        ),
    )
