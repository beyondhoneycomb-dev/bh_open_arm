"""Synthetic fixtures for the WP-4C-03 aggregator tests.

The real rollout population (WP-4C-01/02) is DEFERRED, so these are fabricated
episode outcomes with a fixed `success` count — never a real rollout number. They
exist to exercise the offline math: given a chosen (n_success, n_trials), build a
matching episode set so the aggregator's arithmetic can be checked against the
spec's cited figures and against an independent oracle.
"""

from __future__ import annotations

from backend.eval.stats import EpisodeRecord
from backend.training.lineage import CheckpointId

_DEFAULT_LATENCY_MS = 10.0
_DEFAULT_LENGTH = 100
_FAILURE_TAGS = ("COLLISION",)


def checkpoint(output_dir: str = "/runs/a", step: int = 1000) -> CheckpointId:
    """A WP-4A-05 lineage checkpoint identity for a report."""
    return CheckpointId(output_dir=output_dir, step=step)


def episode(
    success: bool,
    seed: int = 0,
    task_id: str = "pick",
    length: int = _DEFAULT_LENGTH,
    latency_ms: float = _DEFAULT_LATENCY_MS,
    tags: tuple[str, ...] = (),
) -> EpisodeRecord:
    """One synthetic episode; failures carry one safety stop and one collision.

    The safety/collision counts on a failure are fixture furniture so the
    aggregate metrics are non-trivial; they are not a claim about real rollouts.
    """
    return EpisodeRecord(
        task_id=task_id,
        seed=seed,
        success=success,
        episode_length=length,
        collisions=0 if success else 1,
        torque_limit_hits=0 if success else 1,
        safety_stops=0 if success else 1,
        inference_latency_p95=latency_ms,
        failure_tags=() if success else tags,
    )


def episodes_with(
    n_success: int,
    n_trials: int,
    tags: tuple[str, ...] = _FAILURE_TAGS,
) -> list[EpisodeRecord]:
    """Build `n_trials` episodes with exactly `n_success` successes.

    Args:
        n_success: Number of successful episodes, `0 <= n_success <= n_trials`.
        n_trials: Total episodes.
        tags: Failure tags each failing episode carries.

    Returns:
        (list[EpisodeRecord]) The synthetic episode set, seeds 0..n_trials-1.
    """
    if not 0 <= n_success <= n_trials:
        raise ValueError(f"need 0 <= n_success <= n_trials; got {n_success}, {n_trials}")
    return [episode(index < n_success, seed=index, tags=tags) for index in range(n_trials)]


def report(
    n_success: int,
    n_trials: int,
    output_dir: str = "/runs/a",
    step: int = 1000,
    rollout_set_id: str = "rs-1",
    tags: tuple[str, ...] = _FAILURE_TAGS,
):
    """Aggregate a synthetic (n_success, n_trials) into a `SuccessRateReport`."""
    from backend.eval.stats import aggregate

    return aggregate(
        rollout_set_id,
        checkpoint(output_dir, step),
        episodes_with(n_success, n_trials, tags),
    )
