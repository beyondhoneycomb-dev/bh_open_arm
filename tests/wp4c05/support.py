"""Synthetic fixtures for the WP-4C-05 dual-condition protocol tests.

The real rollout population (WP-4C-01/02) and the perturbation execution (Human/HW)
are DEFERRED, so these are fabricated episode outcomes with a chosen success count —
never a real rollout number and never a real perturbed distribution. They exist to
exercise the offline schema: the same-checkpoint refusal, the derived gap, the
Wave-3C-reference guard, seed recording, and the reproducibility-limit statement.

Condition arms are built through `aggregate_condition`, which calls the committed
WP-4C-03 aggregator, so these fixtures also exercise the real consumption path.
"""

from __future__ import annotations

from backend.eval.protocol import (
    Condition,
    ConditionArm,
    PerturbationAxis,
    PerturbationProtocol,
    aggregate_condition,
)
from backend.eval.stats import EpisodeRecord
from backend.training.lineage import CheckpointId

_DEFAULT_LATENCY_MS = 10.0
_DEFAULT_LENGTH = 100
_DEFAULT_CRITERION = "crit-pick-place-v1"


def checkpoint(output_dir: str = "/runs/a", step: int = 1000) -> CheckpointId:
    """A WP-4A-05 lineage checkpoint identity for a condition arm."""
    return CheckpointId(output_dir=output_dir, step=step)


def episodes_with(n_success: int, n_trials: int, seed_base: int = 0) -> list[EpisodeRecord]:
    """Build `n_trials` synthetic episodes with exactly `n_success` successes.

    Seeds are `seed_base .. seed_base + n_trials - 1`, so a NOMINAL and a PERTURBED
    arm can be given distinct seed ranges to prove each records its own seeds.
    """
    if not 0 <= n_success <= n_trials:
        raise ValueError(f"need 0 <= n_success <= n_trials; got {n_success}, {n_trials}")
    return [
        EpisodeRecord(
            task_id="pick",
            seed=seed_base + index,
            success=index < n_success,
            episode_length=_DEFAULT_LENGTH,
            collisions=0 if index < n_success else 1,
            torque_limit_hits=0 if index < n_success else 1,
            safety_stops=0 if index < n_success else 1,
            inference_latency_p95=_DEFAULT_LATENCY_MS,
            failure_tags=() if index < n_success else ("COLLISION",),
        )
        for index in range(n_trials)
    ]


def arm(
    condition: Condition,
    n_success: int,
    n_trials: int,
    output_dir: str = "/runs/a",
    step: int = 1000,
    success_criterion_id: str = _DEFAULT_CRITERION,
    rollout_set_id: str = "rs-1",
    seed_base: int = 0,
) -> ConditionArm:
    """Aggregate a synthetic (n_success, n_trials) into a `ConditionArm` for a condition."""
    return aggregate_condition(
        condition,
        rollout_set_id,
        checkpoint(output_dir, step),
        episodes_with(n_success, n_trials, seed_base=seed_base),
        success_criterion_id,
    )


def axis(
    name: str = "object_x_position",
    distribution_ref: str = "Wave 3C 초기 상태 분포 / pick task",
) -> PerturbationAxis:
    """A perturbation axis that references the Wave 3C initial-state distribution."""
    return PerturbationAxis(name=name, distribution_ref=distribution_ref)


def defined_protocol(task_id: str = "pick") -> PerturbationProtocol:
    """A DEFINED perturbation protocol (the positive control / post-Wave-3C shape)."""
    return PerturbationProtocol.of_axes(task_id, (axis(),))


def deferred_protocol(task_id: str = "pick") -> PerturbationProtocol:
    """The DEFERRED perturbation protocol — the honest phase-1 state (Wave 3C not landed)."""
    return PerturbationProtocol.deferred_pending_wave_3c(task_id)
