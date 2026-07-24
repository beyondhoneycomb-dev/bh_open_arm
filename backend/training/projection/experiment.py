"""The paired torque/velocity ablation experiment generator (`02c` §1.6).

`10` FR-TRN-073 requires that the two arms of the ablation — a FULL policy trained
on the whole `observation.state` and a POS_ONLY policy trained on the `.pos`
subvector — differ in EXACTLY one thing (the projection) and share four controls:

    (a) the same `repo_id` + `revision`,
    (b) the same seed,
    (c) the same rollout set and trial count,
    (d) the same success criterion.

Those four are stored ONCE on `PairedExperiment` and both arms read them from
there, so an experiment whose arms disagree on a control is not representable —
the type has one slot per control, not one per arm. The generator is the second
guard: it takes two independently written `ArmRequest`s (the shape a human copies
and tweaks) and REFUSES to pair them when any of (a)-(d) differ, naming each
mismatch, so the difference cannot be introduced and then trained silently
(`CG-4A-06b`).

The observation subvector is selected by name (`selector.select_pos_indices`), and
the action target is the position-only set for both arms — the projection never
touches the action (`10` FR-TRN-074, `11` FR-INF-074). Observation names come from
the committed WP-4A-02 `ObservationConfig`; the action names are the frozen
`CTR-REC@v1` position-only set for the config's arm count.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.training.preflight import ObservationConfig
from backend.training.projection.selector import (
    ProjectionKind,
    observation_projection_indices,
    select_action_target_indices,
)
from contracts.recorder import action_names

# The two projections the ablation compares; exactly this pair must appear, once
# each (`10` FR-TRN-073). Arm A is the FULL policy, arm B the POS_ONLY policy.
_ARM_A_PROJECTION = ProjectionKind.FULL
_ARM_B_PROJECTION = ProjectionKind.POS_ONLY


class PairedExperimentError(ValueError):
    """Two arm requests could not be paired without violating FR-TRN-073.

    Raised when the arms disagree on a shared control (a)-(d), or when their
    projections are not exactly {FULL, POS_ONLY}. The message names every offending
    field so the operator sees which control drifted.
    """


@dataclass(frozen=True)
class ArmRequest:
    """One arm's training request, as written before the arms are paired.

    This is the shape a human authors and copies, so it carries the four shared
    controls independently and can therefore disagree with its twin — which is the
    exact defect `generate_paired_experiment` refuses.

    Attributes:
        repo_id: The dataset repository id (control (a)).
        revision: The dataset git revision (control (a)).
        seed: The training seed (control (b)).
        rollout_set_id: The evaluation rollout set and trial count id (control (c)).
        success_criterion_id: The success-judgment criterion id (control (d)).
        projection: The observation projection this arm trains on.
    """

    repo_id: str
    revision: str
    seed: int
    rollout_set_id: str
    success_criterion_id: str
    projection: ProjectionKind


@dataclass(frozen=True)
class ExperimentArm:
    """One resolved arm: its projection and the channel sets it trains on.

    The action selection is the position-only set for both arms — only observation
    width differs by projection (`10` FR-TRN-074). Indices are name-derived, so the
    arm records both the indices and the names they select for auditability.

    Attributes:
        label: A human label, e.g. `FULL_48` or `POS_ONLY_16`.
        projection: The observation projection.
        observation_indices: Kept `observation.state` indices, in names order.
        observation_names: The selected observation channel names.
        action_indices: The position-only action-target indices.
        action_names: The selected action channel names (all `.pos`).
    """

    label: str
    projection: ProjectionKind
    observation_indices: tuple[int, ...]
    observation_names: tuple[str, ...]
    action_indices: tuple[int, ...]
    action_names: tuple[str, ...]

    @property
    def observation_dim(self) -> int:
        """The projected observation width."""
        return len(self.observation_indices)

    @property
    def action_dim(self) -> int:
        """The action-target width — position-only, identical across arms."""
        return len(self.action_indices)


@dataclass(frozen=True)
class PairedExperiment:
    """A torque/velocity ablation: two arms sharing four controls by construction.

    The four FR-TRN-073 controls live here once, not on the arms, so the arms cannot
    hold conflicting values — a mismatched experiment is unrepresentable, not merely
    rejected. `arm_a` is the FULL policy and `arm_b` the POS_ONLY policy.

    Attributes:
        repo_id: The shared dataset repository id (control (a)).
        revision: The shared dataset git revision (control (a)).
        seed: The shared training seed (control (b)).
        rollout_set_id: The shared rollout set and trial count id (control (c)).
        success_criterion_id: The shared success-criterion id (control (d)).
        arm_a: The FULL-projection arm.
        arm_b: The POS_ONLY-projection arm.
    """

    repo_id: str
    revision: str
    seed: int
    rollout_set_id: str
    success_criterion_id: str
    arm_a: ExperimentArm
    arm_b: ExperimentArm


def _control_mismatches(arm_a: ArmRequest, arm_b: ArmRequest) -> list[str]:
    """Return one message per FR-TRN-073 control that differs between two requests.

    Args:
        arm_a: The first arm request.
        arm_b: The second arm request.

    Returns:
        (list[str]) A message naming each of (a)-(d) that disagrees; empty when the
            four controls match.
    """
    controls = (
        ("repo_id", arm_a.repo_id, arm_b.repo_id),
        ("revision", arm_a.revision, arm_b.revision),
        ("seed", arm_a.seed, arm_b.seed),
        ("rollout_set_id", arm_a.rollout_set_id, arm_b.rollout_set_id),
        ("success_criterion_id", arm_a.success_criterion_id, arm_b.success_criterion_id),
    )
    return [f"{field}: {left!r} != {right!r}" for field, left, right in controls if left != right]


def _build_arm(
    request: ArmRequest, observation_names: tuple[str, ...], target_names: tuple[str, ...]
) -> ExperimentArm:
    """Resolve one arm's channel selections from its projection.

    Args:
        request: The arm request supplying the projection.
        observation_names: The dataset `observation.state` names.
        target_names: The position-only action names.

    Returns:
        (ExperimentArm) The arm with name-derived observation and action selections.
    """
    observation_indices = observation_projection_indices(observation_names, request.projection)
    action_indices = select_action_target_indices(target_names)
    selected_observation = tuple(observation_names[index] for index in observation_indices)
    label = f"{request.projection.value}_{len(observation_indices)}"
    return ExperimentArm(
        label=label,
        projection=request.projection,
        observation_indices=tuple(observation_indices),
        observation_names=selected_observation,
        action_indices=tuple(action_indices),
        action_names=tuple(target_names[index] for index in action_indices),
    )


def generate_paired_experiment(
    arm_a: ArmRequest, arm_b: ArmRequest, config: ObservationConfig
) -> PairedExperiment:
    """Pair two arm requests into an ablation experiment, or refuse.

    Enforces FR-TRN-073 (a)-(d) as a precondition: the two requests must agree on
    every shared control and must carry exactly the {FULL, POS_ONLY} projections,
    one each. On any violation the pairing is refused rather than the difference
    trained. The action target is the position-only `CTR-REC@v1` set for the
    config's arm count, identical for both arms.

    Args:
        arm_a: The intended FULL arm request.
        arm_b: The intended POS_ONLY arm request.
        config: The committed WP-4A-02 observation configuration supplying the
            `observation.state` names and arm count.

    Returns:
        (PairedExperiment) The paired experiment, controls stored once.

    Raises:
        PairedExperimentError: When a control (a)-(d) differs, or the projections
            are not exactly {FULL, POS_ONLY} with FULL first.
        ActionTargetLeakError: When the config's action names carry a `.vel`/
            `.torque` channel (raised by the action-target chokepoint).
    """
    mismatches = _control_mismatches(arm_a, arm_b)
    if mismatches:
        raise PairedExperimentError(
            "paired arms disagree on FR-TRN-073 controls (a)-(d); the ablation would confound "
            f"the projection with these differences: {mismatches}"
        )
    if (arm_a.projection, arm_b.projection) != (_ARM_A_PROJECTION, _ARM_B_PROJECTION):
        raise PairedExperimentError(
            f"arms must be exactly (arm_a={_ARM_A_PROJECTION.value}, "
            f"arm_b={_ARM_B_PROJECTION.value}); got (arm_a={arm_a.projection.value}, "
            f"arm_b={arm_b.projection.value})"
        )

    observation_names = tuple(config.names)
    target_names = action_names(config.bimanual)

    return PairedExperiment(
        repo_id=arm_a.repo_id,
        revision=arm_a.revision,
        seed=arm_a.seed,
        rollout_set_id=arm_a.rollout_set_id,
        success_criterion_id=arm_a.success_criterion_id,
        arm_a=_build_arm(arm_a, observation_names, target_names),
        arm_b=_build_arm(arm_b, observation_names, target_names),
    )
