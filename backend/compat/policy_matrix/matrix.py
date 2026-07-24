"""The three-axis usable-policy matrix engine (`10` FR-TRN-064/065/017).

The matrix is three axes, not two: {policy} x {dataset observation config} x
{observation projection}. A policy is blocked for a cell when any FR-TRN-017 rule
fires, and the third axis is what CG-4B-01d proves is real — a bimanual 48-dim
recording blocks the 32-capped families, but projecting it to its `.pos` subvector
(16-dim) brings them back, with no edit to any table.

The engine reuses its three inputs rather than restating them:

  * the DIMENSION and structural axes reuse `backend.learning.policy_constraints`
    (WP-0C-07) — the six FR-TRN-017 rules are run there, and this module only
    feeds it introspected ceilings and renders its verdicts with provenance;
  * the OBSERVATION-CONFIG axis is the committed WP-4A-02 `ObservationConfig`,
    consumed by import, so `state_dim` is judged by `names` (FR-TRN-061), never by
    a shape this module re-derives;
  * the PROJECTION axis is the committed WP-4A-06 `observation_projection_indices`,
    consumed by import, so the `.pos` subvector is selected by the same
    name-derived rule the ablation uses, never a positional slice.

Because the ceiling flows from introspection and the width flows from the config
and projection, switching the observation config 24->48 auto-removes the 32-capped
families (CG-4B-01c) and switching the projection to `.pos`-only brings them back
(CG-4B-01d): `usable_policies` simply recomputes, it is never manually refreshed.

The engine's job is to BLOCK. A missing block is the failure mode, not a missing
pass (`10` FR-TRN-064 negative branch): an unblocked 48-dim/32-cap cell lets
training start and `max_state_dim` truncate silently inside LeRobot.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.compat.policy_matrix.capability import (
    RULE_ID_BY_CODE,
    PolicyCapability,
    TrainingDefaults,
    build_capability_registry,
    introspect_training_defaults,
    wave0c_block_code,
)
from backend.compat.policy_matrix.verdict import BlockingReason, CompatibilityVerdict
from backend.learning.policy_constraints import (
    DatasetProfile,
    PolicyConstraintCode,
    PolicySpec,
    PolicyStructuralValidator,
    Violation,
)
from backend.training.preflight import ObservationConfig
from backend.training.projection import ProjectionKind, observation_projection_indices

# The fixed architectural bound the single-observation-step and temporal-ensemble
# rules enforce: ACT reads exactly one observation step and, under temporal
# ensembling, emits exactly one action step (`configuration_act.py`). This is not a
# dimension capability read from the config (those are introspected) but the rule's
# own constant, so it is named here rather than as a bare literal in the renderer.
_SINGLE_STEP = 1


@dataclass(frozen=True)
class TrainingRequest:
    """The tunable knobs the FR-TRN-017 structural rules read for one evaluation.

    A default view fills these from the family's shipped config
    (`TrainingRequest.from_defaults`), so a policy at its own defaults trips no
    structural rule. CG-4B-01e overrides one knob at a time to prove each of the
    six rules blocks independently.

    Attributes:
        n_obs_steps: Observation steps fed to the policy (ACT rule (a)).
        n_action_steps: Action steps per invocation (ACT rules (b), (c)).
        chunk_size: Action-chunk bound (ACT rule (b)).
        temporal_ensemble: Whether temporal ensembling is enabled (ACT rule (c)).
        n_cameras: Camera count in the dataset (VQ-BeT rule (e)).
        has_state: Whether an `observation.state` feature is present (Diffusion
            rule (d)).
    """

    n_obs_steps: int
    n_action_steps: int
    chunk_size: int
    temporal_ensemble: bool
    n_cameras: int
    has_state: bool

    @classmethod
    def from_defaults(cls, defaults: TrainingDefaults) -> TrainingRequest:
        """Build a request from a family's introspected shipped defaults.

        Args:
            defaults: The family's shipped structural knobs.

        Returns:
            (TrainingRequest) A request that trips no structural rule the shipped
                config would not.
        """
        return cls(
            n_obs_steps=defaults.n_obs_steps,
            n_action_steps=defaults.n_action_steps,
            chunk_size=defaults.chunk_size,
            temporal_ensemble=defaults.temporal_ensemble,
            n_cameras=defaults.n_cameras,
            has_state=defaults.has_state,
        )


@dataclass(frozen=True)
class CompatibilityMatrix:
    """The compatibility calculator over an introspected capability registry.

    Attributes:
        capabilities: Family id to its source-derived capability.
        defaults: Family id to its shipped structural knobs, used when an
            evaluation supplies no explicit request.
    """

    capabilities: dict[str, PolicyCapability]
    defaults: dict[str, TrainingDefaults]

    def policies(self) -> tuple[str, ...]:
        """Return the registered policy families, in registry order."""
        return tuple(self.capabilities)

    def evaluate(
        self,
        policy_id: str,
        observation_config: ObservationConfig,
        projection: ProjectionKind,
        request: TrainingRequest | None = None,
    ) -> CompatibilityVerdict:
        """Evaluate one {policy, observation-config, projection} triple.

        Args:
            policy_id: A registered policy family.
            observation_config: The committed WP-4A-02 observation configuration.
            projection: The observation projection (WP-4A-06); POS_ONLY selects the
                `.pos` subvector, FULL keeps every recorded channel.
            request: The structural knobs; defaults to the family's shipped config
                when omitted.

        Returns:
            (CompatibilityVerdict) The verdict, carrying every blocking reason with
                its source.
        """
        capability = self.capabilities[policy_id]
        effective_request = request or TrainingRequest.from_defaults(self.defaults[policy_id])
        state_dim = len(observation_projection_indices(observation_config.names, projection))
        action_dim = observation_config.action_dim

        spec = PolicySpec(
            policy_type=policy_id,
            n_obs_steps=effective_request.n_obs_steps,
            n_action_steps=effective_request.n_action_steps,
            chunk_size=effective_request.chunk_size,
            temporal_ensemble=effective_request.temporal_ensemble,
            max_state_dim=capability.max_state_dim,
            max_action_dim=capability.max_action_dim,
        )
        profile = DatasetProfile(
            state_dim=state_dim,
            action_dim=action_dim,
            n_cameras=effective_request.n_cameras,
            has_state=effective_request.has_state,
        )
        reasons = tuple(
            _render_reason(violation, spec, profile, capability)
            for violation in PolicyStructuralValidator().validate(spec, profile)
        )
        return CompatibilityVerdict(
            policy_id=policy_id, allowed=not reasons, blocking_reasons=reasons
        )

    def usable_policies(
        self,
        observation_config: ObservationConfig,
        projection: ProjectionKind,
        request: TrainingRequest | None = None,
    ) -> tuple[str, ...]:
        """Return the families whose cell is allowed for this config and projection.

        This is the "usable policy matrix" of `10` FR-TRN-065: because the ceiling
        is introspected and the width is derived from the config and projection,
        flipping the observation config 24->48 drops the 32-capped families and
        projecting to `.pos`-only brings them back, both with no manual edit.

        Args:
            observation_config: The committed WP-4A-02 observation configuration.
            projection: The observation projection.
            request: An optional shared request; when omitted each family is judged
                at its own shipped defaults.

        Returns:
            (tuple[str, ...]) Allowed policy families, in registry order.
        """
        return tuple(
            policy_id
            for policy_id in self.capabilities
            if self.evaluate(policy_id, observation_config, projection, request).allowed
        )


def build_matrix() -> CompatibilityMatrix:
    """Build a calculator from the installed LeRobot configs.

    Returns:
        (CompatibilityMatrix) A calculator whose ceilings are introspected off the
            installed policy configs, never copied.
    """
    capabilities = build_capability_registry()
    defaults = {policy_id: introspect_training_defaults(policy_id) for policy_id in capabilities}
    return CompatibilityMatrix(capabilities=capabilities, defaults=defaults)


def _render_reason(
    violation: Violation,
    spec: PolicySpec,
    profile: DatasetProfile,
    capability: PolicyCapability,
) -> BlockingReason:
    """Turn a validator violation into a source-attributed blocking reason.

    The four FR-TRN-004 fields are computed from the spec/profile/capability the
    caller already holds, never parsed from the violation message, so `observed`,
    `limit` and `source` are structured values a 창구 can render.

    Args:
        violation: The rule the WP-0C-07 validator raised.
        spec: The policy spec the validator was run against.
        profile: The dataset profile the validator was run against.
        capability: The introspected capability supplying the source file.

    Returns:
        (BlockingReason) The reason with rule id, field, observed, limit and source.
    """
    rule_id = RULE_ID_BY_CODE[violation.code]
    source = capability.source

    if violation.code is PolicyConstraintCode.DIMENSION_CAP_EXCEEDED:
        return _render_dimension_reason(rule_id, profile, capability)
    if violation.code is PolicyConstraintCode.ACT_MULTIPLE_OBS_STEPS:
        return BlockingReason(
            rule_id=rule_id,
            field_name="n_obs_steps",
            observed=spec.n_obs_steps,
            limit=_SINGLE_STEP,
            source=source,
            message=(
                f"ACT reads a single observation step; n_obs_steps={spec.n_obs_steps} "
                f"exceeds {_SINGLE_STEP} ({rule_id})"
            ),
        )
    if violation.code is PolicyConstraintCode.ACT_ACTION_STEPS_EXCEED_CHUNK:
        return BlockingReason(
            rule_id=rule_id,
            field_name="n_action_steps",
            observed=spec.n_action_steps,
            limit=spec.chunk_size,
            source=source,
            message=(
                f"ACT bounds n_action_steps by chunk_size; n_action_steps="
                f"{spec.n_action_steps} exceeds chunk_size={spec.chunk_size} ({rule_id})"
            ),
        )
    if violation.code is PolicyConstraintCode.TEMPORAL_ENSEMBLE_ACTION_STEPS:
        return BlockingReason(
            rule_id=rule_id,
            field_name="n_action_steps",
            observed=spec.n_action_steps,
            limit=_SINGLE_STEP,
            source=source,
            message=(
                f"temporal ensembling requires n_action_steps={_SINGLE_STEP}; got "
                f"{spec.n_action_steps} ({rule_id})"
            ),
        )
    if violation.code is PolicyConstraintCode.DIFFUSION_MISSING_STATE:
        return BlockingReason(
            rule_id=rule_id,
            field_name="observation.state",
            observed="absent",
            limit="required",
            source=source,
            message=f"Diffusion requires an observation.state feature; none present ({rule_id})",
        )
    return BlockingReason(
        rule_id=rule_id,
        field_name="n_cameras",
        observed=profile.n_cameras,
        limit=_SINGLE_STEP,
        source=source,
        message=(
            f"VQ-BeT accepts a single camera; n_cameras={profile.n_cameras} exceeds "
            f"{_SINGLE_STEP} ({rule_id})"
        ),
    )


def _render_dimension_reason(
    rule_id: str,
    profile: DatasetProfile,
    capability: PolicyCapability,
) -> BlockingReason:
    """Render the FR-TRN-064 dimension block, naming the axis that overran.

    Args:
        rule_id: The dimension rule id (`FR-TRN-017f`).
        profile: The dataset profile carrying the observed widths.
        capability: The introspected capability supplying the ceilings and source.

    Returns:
        (BlockingReason) A reason whose `field_name`/`limit` name the exceeded
            ceiling (`max_state_dim` or `max_action_dim`) and whose message carries
            the Wave 0-C authored block code.
    """
    code = wave0c_block_code(capability.policy_id)
    code_note = f" [{code}]" if code else ""
    state_dim = profile.state_dim
    if (
        capability.max_state_dim is not None
        and state_dim is not None
        and state_dim > capability.max_state_dim
    ):
        return BlockingReason(
            rule_id=rule_id,
            field_name="max_state_dim",
            observed=state_dim,
            limit=capability.max_state_dim,
            source=capability.source,
            message=(
                f"observation.state width {state_dim} exceeds max_state_dim "
                f"{capability.max_state_dim}{code_note} ({rule_id}); read from "
                f"{capability.source}"
            ),
        )
    limit = capability.max_action_dim if capability.max_action_dim is not None else 0
    return BlockingReason(
        rule_id=rule_id,
        field_name="max_action_dim",
        observed=profile.action_dim,
        limit=limit,
        source=capability.source,
        message=(
            f"action width {profile.action_dim} exceeds max_action_dim {limit}{code_note} "
            f"({rule_id}); read from {capability.source}"
        ),
    )
