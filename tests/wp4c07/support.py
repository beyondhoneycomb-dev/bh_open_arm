"""Builders that ground the WP-4C-07 gates on the committed contracts, not mocks.

The success labels this WP compares are attached to the committed WP-4C-03
`EpisodeRecord` and the failure tags are committed WP-4C-04 `FailureTag` VALUES, so the
tests exercise the same shapes a real (DEFERRED) rollout + human label would produce —
never a hand-forged record type. No real VLM run and no human labels are fabricated:
the judge is a synthetic, injectable verdict and the "human" label is a given input.
"""

from __future__ import annotations

from backend.eval.autojudge.adapter import JudgeRequest, JudgeVerdict, VlmJudge
from backend.eval.autojudge.agreement import JudgmentPair
from backend.eval.autojudge.labels import (
    JudgedEpisode,
    JudgeSidecar,
    LabelSource,
)
from backend.eval.stats.episode import EpisodeRecord

_EPISODE_LENGTH = 100
_LATENCY_P95_MS = 12.0
_MODEL_NAME = "cosmos-reason-2"


def episode(
    task_id: str,
    seed: int,
    success: bool,
    failure_tags: tuple[str, ...] = (),
) -> EpisodeRecord:
    """Return a valid committed `EpisodeRecord` with healthy defaults.

    Args:
        task_id: The task the episode ran.
        seed: The initial-state seed (episode identity with `task_id`).
        success: The success label.
        failure_tags: Failure-tag values (empty on success).

    Returns:
        (EpisodeRecord) A record that passes `EpisodeRecord.validate`.
    """
    return EpisodeRecord(
        task_id=task_id,
        seed=seed,
        success=success,
        episode_length=_EPISODE_LENGTH,
        collisions=0,
        torque_limit_hits=0,
        safety_stops=0,
        inference_latency_p95=_LATENCY_P95_MS,
        failure_tags=failure_tags,
    )


def human(
    task_id: str,
    seed: int,
    success: bool,
    failure_tags: tuple[str, ...] = (),
) -> JudgedEpisode:
    """Return a HUMAN-sourced labelled episode (the canon source)."""
    return JudgedEpisode(
        episode=episode(task_id, seed, success, failure_tags),
        source=LabelSource.HUMAN,
    )


def model(
    task_id: str,
    seed: int,
    success: bool,
    rationale: str = "synthetic verdict",
) -> JudgedEpisode:
    """Return a MODEL-sourced labelled episode with a `model-judged` sidecar."""
    return JudgedEpisode(
        episode=episode(task_id, seed, success),
        source=LabelSource.MODEL,
        sidecar=JudgeSidecar(model_name=_MODEL_NAME, rationale=rationale),
    )


def pair(
    task_id: str,
    seed: int,
    human_success: bool,
    model_success: bool,
    human_failure_tags: tuple[str, ...] = (),
) -> JudgmentPair:
    """Return a human/model judgement pair for one episode."""
    return JudgmentPair(
        task_id=task_id,
        seed=seed,
        human_success=human_success,
        model_success=model_success,
        human_failure_tags=human_failure_tags,
    )


class ConstantJudge(VlmJudge):
    """A synthetic judge that returns a fixed verdict — no model weights, no video.

    Stands in for the DEFERRED Cosmos Reason 2 run so the adapter and disagreement
    paths are exercised without fabricating a real rollout label.
    """

    def __init__(self, success: bool, rationale: str = "synthetic verdict") -> None:
        """Bind the fixed verdict this judge always returns."""
        self.mSuccess = success
        self.mRationale = rationale

    def judge(self, request: JudgeRequest) -> JudgeVerdict:
        """Return the fixed verdict, ignoring the request contents."""
        return JudgeVerdict(success=self.mSuccess, rationale=self.mRationale)
