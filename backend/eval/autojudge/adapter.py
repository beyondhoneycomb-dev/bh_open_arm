"""The VLM auto-judge adapter (Cosmos Reason 2) — interface, not a live model run.

`FR-SIM-095` fixes the shape: the evaluation critic takes a rollout video plus a task
prompt and returns success/fail with a rationale, recorded as `model-judged` sidecar
metadata. This module is that adapter surface. The REAL model run is DEFERRED — the
rollout video (WP-4C-01) and the GPU-resident Cosmos Reason 2 weights are Human/HW
bands not landed here — so `CosmosReason2Judge` refuses to invent a verdict, and the
package is exercised through an injected judge on synthetic inputs.

The adapter's product is always a MODEL-sourced `JudgedEpisode`: a verdict, its
rationale, and a `model-judged` sidecar. It can never emit a HUMAN label — that would
launder a model judgement into the canon (`FR-INF-079`) — so `judge_episode` fixes
`source=MODEL` and there is no parameter to override it.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol

from backend.eval.autojudge.constants import COSMOS_REASON_2
from backend.eval.autojudge.labels import (
    JudgedEpisode,
    JudgeSidecar,
    LabelSource,
)
from backend.eval.stats.episode import EpisodeRecord


class AutoJudgeDeferredError(NotImplementedError):
    """Raised when the real VLM judge is asked for a verdict it cannot produce.

    The live Cosmos Reason 2 run is DEFERRED: no rollout video and no GPU-resident
    model are present in this AI-offline phase. Refusing here keeps the code from
    fabricating a rollout label — the one thing `FR-INF-079` and this WP forbid.
    """


@dataclass(frozen=True)
class JudgeRequest:
    """One auto-judge request (`FR-SIM-095` input = 롤아웃 영상 + 태스크 프롬프트).

    Attributes:
        task_id: The task the episode ran (also the join key into the human labels).
        seed: The episode's recorded initial-state seed — with `task_id`, the
            reproducible episode identity (`FR-SIM-056`).
        task_prompt: The natural-language success criterion the judge evaluates
            against. Empty is refused by the real adapter: without the §3.7 step-(2)
            criterion prose there is nothing to prompt the VLM with.
        video_ref: A reference to the rollout video (a path/URI). The bytes are not
            resolved here; the real run is DEFERRED.
    """

    task_id: str
    seed: int
    task_prompt: str
    video_ref: str


@dataclass(frozen=True)
class JudgeVerdict:
    """The judge's raw output before it is bound to an episode (`FR-SIM-095` output).

    Attributes:
        success: The judged success label.
        rationale: The judge's stated reason (성공/실패 + 근거).
    """

    success: bool
    rationale: str


class VlmJudge(Protocol):
    """The auto-judge callable surface `judge_episode` drives.

    A judge maps a `JudgeRequest` to a `JudgeVerdict`. Kept a Protocol so the real
    Cosmos Reason 2 adapter and a synthetic test judge are interchangeable, and so no
    test needs the model weights to exercise the disagreement/trigger paths.
    """

    def judge(self, request: JudgeRequest) -> JudgeVerdict:
        """Return the judge's verdict for one request."""
        ...


class CosmosReason2Judge:
    """The real Cosmos Reason 2 adapter — a placeholder that refuses to fabricate.

    `FR-SIM-095` names Cosmos Reason 2 as the critic; running it needs the rollout
    video and a Hopper/Blackwell GPU (see `preflight`), neither present offline. So
    this adapter records its identity but raises on `judge`: the label it would return
    is a rollout number, and this WP never fakes one.
    """

    def __init__(self) -> None:
        """Bind the judge's model identity for sidecar attribution."""
        self.mModelName = COSMOS_REASON_2

    def judge(self, request: JudgeRequest) -> JudgeVerdict:
        """Refuse to judge: the live run is DEFERRED (raises `AutoJudgeDeferredError`)."""
        raise AutoJudgeDeferredError(
            f"Cosmos Reason 2 run is deferred (no rollout video / GPU): cannot judge "
            f"{request.task_id!r} seed {request.seed}"
        )


def judge_episode(
    judge: VlmJudge,
    request: JudgeRequest,
    episode: EpisodeRecord,
    model_name: str,
) -> JudgedEpisode:
    """Run the auto-judge for one episode and bind it as a MODEL-sourced label.

    The verdict overwrites only the `success` field of the supplied committed
    `EpisodeRecord` (via `dataclasses.replace`); every other recorded fact — seed,
    counts, latency, failure tags — is the episode's own. The result is always
    `source=MODEL` with a `model-judged` sidecar, so the adapter cannot launder a
    model judgement into the canon (`FR-INF-079`).

    Args:
        judge: The judge to run (real adapter or injected synthetic judge).
        request: The rollout-video + prompt request.
        episode: The committed episode record the label attaches to; its `task_id`
            and `seed` must match the request (else it is a different episode).
        model_name: The judge identity to stamp in the sidecar.

    Returns:
        (JudgedEpisode) A MODEL-sourced labelled episode with its judge sidecar.

    Raises:
        ValueError: When the request and episode identify different episodes.
        AutoJudgeDeferredError: When `judge` is the real, deferred adapter.
    """
    if (request.task_id, request.seed) != (episode.task_id, episode.seed):
        raise ValueError(
            "judge request and episode identify different episodes: "
            f"request=({request.task_id!r}, {request.seed}) "
            f"episode=({episode.task_id!r}, {episode.seed})"
        )
    verdict = judge.judge(request)
    judged_record = replace(episode, success=verdict.success)
    sidecar = JudgeSidecar(model_name=model_name, rationale=verdict.rationale)
    return JudgedEpisode(episode=judged_record, source=LabelSource.MODEL, sidecar=sidecar)
