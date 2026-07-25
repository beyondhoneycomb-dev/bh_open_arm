"""The VLM adapter — binds a MODEL label, and the real run stays DEFERRED.

`FR-SIM-095` shapes the adapter (rollout video + prompt -> success/fail + rationale).
The real Cosmos Reason 2 run is DEFERRED, so `CosmosReason2Judge` refuses to fabricate
a verdict, and `judge_episode` (driven by a synthetic judge) always produces a
MODEL-sourced label with a `model-judged` sidecar — it can never emit a human label.
"""

from __future__ import annotations

import pytest

from backend.eval.autojudge import (
    CosmosReason2Judge,
    JudgeRequest,
    LabelSource,
    judge_episode,
)
from backend.eval.autojudge.adapter import AutoJudgeDeferredError
from backend.eval.autojudge.constants import COSMOS_REASON_2
from tests.wp4c07.support import ConstantJudge, episode


def _request(task_id: str, seed: int) -> JudgeRequest:
    """Build a judge request for one episode."""
    return JudgeRequest(
        task_id=task_id,
        seed=seed,
        task_prompt="the cube is inside the bin",
        video_ref=f"rollouts/{task_id}/{seed}.mp4",
    )


def test_real_adapter_refuses_to_fabricate() -> None:
    """The real Cosmos Reason 2 adapter raises — no video, no GPU, no fake label."""
    with pytest.raises(AutoJudgeDeferredError):
        CosmosReason2Judge().judge(_request("pick", 1))


def test_judge_episode_binds_model_label_and_sidecar() -> None:
    """A synthetic judge's verdict becomes a MODEL label with a model-judged sidecar."""
    ep = episode("pick", 1, success=False)
    judged = judge_episode(
        ConstantJudge(success=True, rationale="cube in bin"),
        _request("pick", 1),
        ep,
        model_name=COSMOS_REASON_2,
    )
    assert judged.source is LabelSource.MODEL
    assert judged.episode.success is True  # verdict overrode the record's success
    assert judged.episode.seed == 1  # every other fact preserved
    assert judged.sidecar is not None
    assert judged.sidecar.rationale == "cube in bin"
    assert judged.sidecar.model_name == COSMOS_REASON_2


def test_judge_episode_refuses_identity_mismatch() -> None:
    """A request and episode that name different episodes are refused."""
    with pytest.raises(ValueError, match="different episodes"):
        judge_episode(
            ConstantJudge(success=True),
            _request("pick", 1),
            episode("pick", 2, success=False),
            model_name=COSMOS_REASON_2,
        )


def test_judge_episode_never_produces_a_human_label() -> None:
    """Whatever the verdict, the adapter output is MODEL-sourced, never HUMAN."""
    for verdict in (True, False):
        judged = judge_episode(
            ConstantJudge(success=verdict),
            _request("pick", 7),
            episode("pick", 7, success=not verdict),
            model_name=COSMOS_REASON_2,
        )
        assert judged.source is LabelSource.MODEL
