"""FR-TRN-017 structural pre-validation: block an unbuildable policy/dataset pair.

`10` FR-TRN-017 requires that six structural constraints are checked *before*
training starts, and — critically — that each violation is reported under its own
distinct code, never collapsed into one generic "training config invalid". A
merged report cannot tell an operator whether the fix is to change the policy, the
observation configuration, or the number of cameras.

The six conditions, each in its own check method below, mirror the assertions the
real LeRobot policy configs raise (`configuration_act.py.__post_init__`,
`configuration_diffusion.py`, `configuration_vqbet.py`, and the `max_state_dim`
caps in `configuration_smolvla.py` / `configuration_pi0.py`):

1. ACT with `n_obs_steps != 1`.
2. ACT with `n_action_steps > chunk_size`.
3. Temporal ensembling with `n_action_steps != 1`.
4. Diffusion with no `observation.state` feature.
5. VQ-BeT with two or more cameras.
6. Any dimension-capped policy whose state or action dimension exceeds the cap
   (FR-TRN-064).

This is a pre-check over declared configuration; it does not construct a policy
(that needs the model weights and torch). It states what the real config would
reject, and why, one code at a time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class PolicyConstraintCode(StrEnum):
    """The distinct block codes, one per FR-TRN-017 condition.

    Distinctness is the contract: acceptance ④ requires a fixture that violates
    exactly one condition to surface exactly that condition's code, so these must
    never be folded together.
    """

    ACT_MULTIPLE_OBS_STEPS = "ACT_MULTIPLE_OBS_STEPS"
    ACT_ACTION_STEPS_EXCEED_CHUNK = "ACT_ACTION_STEPS_EXCEED_CHUNK"
    TEMPORAL_ENSEMBLE_ACTION_STEPS = "TEMPORAL_ENSEMBLE_ACTION_STEPS"
    DIFFUSION_MISSING_STATE = "DIFFUSION_MISSING_STATE"
    VQBET_MULTIPLE_CAMERAS = "VQBET_MULTIPLE_CAMERAS"
    DIMENSION_CAP_EXCEEDED = "DIMENSION_CAP_EXCEEDED"


@dataclass(frozen=True)
class Violation:
    """One blocked constraint.

    Attributes:
        code: The machine-readable constraint code.
        message: A human sentence naming the values that triggered the block.
    """

    code: PolicyConstraintCode
    message: str


@dataclass(frozen=True)
class PolicySpec:
    """The policy configuration the constraints are checked against.

    Only the fields the six conditions read are modelled; a real policy config
    carries far more. `policy_type` selects which conditions apply, exactly as the
    real per-policy `__post_init__` does.

    Attributes:
        policy_type: `act` / `diffusion` / `vqbet` / `smolvla` / `pi0` / `pi05`.
        n_obs_steps: Observation steps fed to the policy (ACT).
        n_action_steps: Action steps executed per invocation (ACT).
        chunk_size: Action-chunk upper bound (ACT).
        temporal_ensemble: Whether temporal ensembling is enabled (ACT).
        max_state_dim: State-dimension cap, or None when the policy has none.
        max_action_dim: Action-dimension cap, or None when the policy has none.
    """

    policy_type: str
    n_obs_steps: int = 1
    n_action_steps: int = 1
    chunk_size: int = 100
    temporal_ensemble: bool = False
    max_state_dim: int | None = None
    max_action_dim: int | None = None


@dataclass(frozen=True)
class DatasetProfile:
    """The dataset configuration the constraints are checked against.

    Attributes:
        state_dim: Length of the `observation.state` vector, or None when absent.
        action_dim: Length of the `action` vector.
        n_cameras: Number of camera image/video features.
        has_state: Whether an `observation.state` feature is present.
    """

    state_dim: int | None
    action_dim: int
    n_cameras: int = 0
    has_state: bool = True


# Dimension-capped policy families and their default caps (`10` FR-TRN-064;
# `configuration_smolvla.py`/`configuration_pi0.py` `max_state_dim = 32`). The cap
# a caller passes on `PolicySpec` overrides this, so an introspected value wins;
# this table only supplies the default when the spec leaves the cap unset.
_DEFAULT_DIMENSION_CAPS: dict[str, int] = {
    "smolvla": 32,
    "pi0": 32,
    "pi05": 32,
}


@dataclass
class PolicyStructuralValidator:
    """Run the six FR-TRN-017 conditions and collect one code per violation.

    Each condition is a separate method appending at most one `Violation`. A
    condition that does not apply to the policy type contributes nothing, so the
    returned list contains exactly the conditions that were both applicable and
    violated — never a merged verdict.
    """

    violations: list[Violation] = field(default_factory=list)

    def validate(self, policy: PolicySpec, dataset: DatasetProfile) -> tuple[Violation, ...]:
        """Check `policy` against `dataset` and return every distinct violation.

        Args:
            policy: The policy configuration.
            dataset: The dataset configuration.

        Returns:
            (tuple[Violation, ...]) One entry per violated condition, in condition
            order, each carrying its own distinct code.
        """
        self.violations = []
        self._check_act_obs_steps(policy)
        self._check_act_action_steps_vs_chunk(policy)
        self._check_temporal_ensemble_action_steps(policy)
        self._check_diffusion_requires_state(policy, dataset)
        self._check_vqbet_camera_count(policy, dataset)
        self._check_dimension_cap(policy, dataset)
        return tuple(self.violations)

    def _check_act_obs_steps(self, policy: PolicySpec) -> None:
        """ACT does not handle multiple observation steps (`configuration_act.py`)."""
        if policy.policy_type != "act":
            return
        if policy.n_obs_steps != 1:
            self.violations.append(
                Violation(
                    PolicyConstraintCode.ACT_MULTIPLE_OBS_STEPS,
                    f"ACT requires n_obs_steps == 1; got {policy.n_obs_steps}",
                )
            )

    def _check_act_action_steps_vs_chunk(self, policy: PolicySpec) -> None:
        """The chunk size is the upper bound for action steps (`configuration_act.py`)."""
        if policy.policy_type != "act":
            return
        if policy.n_action_steps > policy.chunk_size:
            self.violations.append(
                Violation(
                    PolicyConstraintCode.ACT_ACTION_STEPS_EXCEED_CHUNK,
                    f"ACT requires n_action_steps <= chunk_size; got "
                    f"n_action_steps={policy.n_action_steps}, chunk_size={policy.chunk_size}",
                )
            )

    def _check_temporal_ensemble_action_steps(self, policy: PolicySpec) -> None:
        """Temporal ensembling requires querying every step (`configuration_act.py`)."""
        if policy.policy_type != "act":
            return
        if policy.temporal_ensemble and policy.n_action_steps != 1:
            self.violations.append(
                Violation(
                    PolicyConstraintCode.TEMPORAL_ENSEMBLE_ACTION_STEPS,
                    "temporal ensembling requires n_action_steps == 1; got "
                    f"{policy.n_action_steps}",
                )
            )

    def _check_diffusion_requires_state(self, policy: PolicySpec, dataset: DatasetProfile) -> None:
        """Diffusion requires `observation.state` as an input (`configuration_diffusion.py`)."""
        if policy.policy_type != "diffusion":
            return
        if not dataset.has_state:
            self.violations.append(
                Violation(
                    PolicyConstraintCode.DIFFUSION_MISSING_STATE,
                    "Diffusion requires an observation.state feature; the dataset has none",
                )
            )

    def _check_vqbet_camera_count(self, policy: PolicySpec, dataset: DatasetProfile) -> None:
        """VQ-BeT accepts exactly one camera (`configuration_vqbet.py`)."""
        if policy.policy_type != "vqbet":
            return
        if dataset.n_cameras >= 2:
            self.violations.append(
                Violation(
                    PolicyConstraintCode.VQBET_MULTIPLE_CAMERAS,
                    f"VQ-BeT accepts a single camera; the dataset has {dataset.n_cameras}",
                )
            )

    def _check_dimension_cap(self, policy: PolicySpec, dataset: DatasetProfile) -> None:
        """A dimension-capped policy rejects a dataset over its cap (`10` FR-TRN-064)."""
        state_cap = policy.max_state_dim
        action_cap = policy.max_action_dim
        default_cap = _DEFAULT_DIMENSION_CAPS.get(policy.policy_type)
        if state_cap is None:
            state_cap = default_cap
        if action_cap is None:
            action_cap = default_cap
        if state_cap is None and action_cap is None:
            return

        if (
            state_cap is not None
            and dataset.state_dim is not None
            and dataset.state_dim > state_cap
        ):
            self.violations.append(
                Violation(
                    PolicyConstraintCode.DIMENSION_CAP_EXCEEDED,
                    f"state_dim {dataset.state_dim} > max_state_dim {state_cap}",
                )
            )
            return
        if action_cap is not None and dataset.action_dim > action_cap:
            self.violations.append(
                Violation(
                    PolicyConstraintCode.DIMENSION_CAP_EXCEEDED,
                    f"action_dim {dataset.action_dim} > max_action_dim {action_cap}",
                )
            )
