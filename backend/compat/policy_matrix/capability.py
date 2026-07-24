"""Source-derived policy capability registry (WP-4B-01, `10` FR-TRN-064/017/004).

The capability values a policy imposes on a dataset — the state/action dimension
ceilings, the `observation.state` normalization mode, the camera constraint, the
structural rules — are READ from the installed LeRobot config class at runtime,
never copied into a constant. FR-TRN-064 is `[확정]`: `max_state_dim` is 32 for
SmolVLA/pi0/pi05 and 132 for GR00T *on the current pin*, and a hardcoded 32 lies
the moment the pin moves a ceiling (CG-4B-01f). So every field of
`PolicyCapability` is introspected off the config dataclass and carries that
config's own source file as its provenance — which is what the blocking renderer
prints as the `source` of every reason (FR-TRN-004: a spec shown without its
source is `[미확인]`).

The config CLASS is resolved through LeRobot's own policy registry
(`PreTrainedConfig.get_choice_class`) rather than a hardcoded class import, so the
binding from a family name to its config class also moves with the pin.

The six FR-TRN-017 structural rules are NOT re-implemented here. Applicability is
probed from their canonical owner, `backend.learning.policy_constraints`
(WP-0C-07): `structural_rules` reports exactly the rules that validator applies to
the family, computed by asking it, so this module invents no rule of its own.

The Wave 0-C policy compatibility matrix (`contracts/policy_compat.yaml`, loaded
via `backend.policy_matrix.registry`) is consumed as the initial data: its
authored block-reason code is reused for the dimension block, and
`crosscheck_wave0c` proves this engine's live introspection still agrees with the
ceilings that document recorded — a drift between the two is a rejected build, not
a silent divergence.
"""

from __future__ import annotations

import dataclasses
import importlib
import inspect
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from backend.learning.policy_constraints import (
    DatasetProfile,
    PolicyConstraintCode,
    PolicySpec,
    PolicyStructuralValidator,
)
from backend.policy_matrix.registry import load_registry

# The policy families WP-4B-01 ranks: the six LeRobot-native families the training
# band offers (`10` FR-TRN-017 names ACT/Diffusion/VQ-BeT explicitly; SmolVLA/pi0/
# pi05 are the 32-capped set of FR-TRN-064) plus GR00T, the 132-capped family that
# clears bimanual 48 (CG-4B-01b). This is the evaluation SCOPE, not a capability
# value: no dimension ceiling is written here — every ceiling is introspected. The
# name→config-class binding is resolved at runtime off LeRobot's registry, so this
# list carries family names only, never a class or a number.
POLICY_FAMILIES: tuple[str, ...] = (
    "smolvla",
    "pi0",
    "pi05",
    "act",
    "diffusion",
    "vqbet",
    "groot",
)

# The config module each family registers itself from. Importing the module runs
# its `@PreTrainedConfig.register_subclass(...)` decorator, which is what populates
# LeRobot's choice registry; without the import `get_choice_class` cannot resolve
# the family. The class is never named here — only the module is imported, then the
# family name resolves the class through the registry.
_CONFIG_MODULES: dict[str, str] = {
    "smolvla": "lerobot.policies.smolvla.configuration_smolvla",
    "pi0": "lerobot.policies.pi0.configuration_pi0",
    "pi05": "lerobot.policies.pi05.configuration_pi05",
    "act": "lerobot.policies.act.configuration_act",
    "diffusion": "lerobot.policies.diffusion.configuration_diffusion",
    "vqbet": "lerobot.policies.vqbet.configuration_vqbet",
    "groot": "lerobot.policies.groot.configuration_groot",
}

_MAX_STATE_DIM_FIELD = "max_state_dim"
_MAX_ACTION_DIM_FIELD = "max_action_dim"
_NORMALIZATION_MAPPING_FIELD = "normalization_mapping"
_STATE_NORM_KEY = "STATE"
_NORM_MODE_UNKNOWN = "UNKNOWN"

# The FR-TRN-017 sub-rule ids, one per condition (`10` §3). (f) — the dimension
# ceiling — is FR-TRN-064 restated as the sixth structural rule.
RULE_ACT_OBS_STEPS = "FR-TRN-017a"
RULE_ACT_ACTION_STEPS = "FR-TRN-017b"
RULE_TEMPORAL_ENSEMBLE = "FR-TRN-017c"
RULE_DIFFUSION_STATE = "FR-TRN-017d"
RULE_VQBET_CAMERAS = "FR-TRN-017e"
RULE_DIMENSION_CAP = "FR-TRN-017f"

# The validator's machine code -> the FR-TRN-017 sub-rule id. Keyed by the
# canonical owner's enum so a renamed code fails to import here rather than
# silently mapping to nothing.
RULE_ID_BY_CODE: dict[PolicyConstraintCode, str] = {
    PolicyConstraintCode.ACT_MULTIPLE_OBS_STEPS: RULE_ACT_OBS_STEPS,
    PolicyConstraintCode.ACT_ACTION_STEPS_EXCEED_CHUNK: RULE_ACT_ACTION_STEPS,
    PolicyConstraintCode.TEMPORAL_ENSEMBLE_ACTION_STEPS: RULE_TEMPORAL_ENSEMBLE,
    PolicyConstraintCode.DIFFUSION_MISSING_STATE: RULE_DIFFUSION_STATE,
    PolicyConstraintCode.VQBET_MULTIPLE_CAMERAS: RULE_VQBET_CAMERAS,
    PolicyConstraintCode.DIMENSION_CAP_EXCEEDED: RULE_DIMENSION_CAP,
}


class CameraConstraint(StrEnum):
    """The camera-count constraint a policy family imposes.

    `SINGLE` is the VQ-BeT case: `configuration_vqbet.py` refuses any input that is
    not exactly one image feature, so two or more cameras is a structural block
    (FR-TRN-017(e)). `NONE` means the family imposes no camera-count rule. The
    value is derived from whether the VQ-BeT rule is applicable to the family, not
    from a hardcoded per-family table.
    """

    NONE = "NONE"
    SINGLE = "SINGLE"


@dataclass(frozen=True)
class PolicyCapability:
    """What a policy family requires of a dataset, read from its installed config.

    Every field is introspected off the config dataclass; none is a copied
    constant (CG-4B-01f). `source` is the provenance FR-TRN-004 requires — the
    blocking renderer prints it as the `source` of every dimension reason.

    Attributes:
        policy_id: The policy family, e.g. `smolvla`.
        max_state_dim: The `observation.state` ceiling read from the config, or
            None when the family declares none (ACT/Diffusion/VQ-BeT are uncapped).
        max_action_dim: The `action` ceiling, or None when uncapped.
        norm_mode: The STATE normalization mode name from the config's
            `normalization_mapping` (e.g. `MEAN_STD`, `QUANTILES`) — pi05 reports
            `QUANTILES`, the q01/q99 requirement of FR-TRN-020.
        camera_constraint: Whether the family requires a single camera.
        structural_rules: The FR-TRN-017 sub-rule ids applicable to this family,
            probed from the WP-0C-07 validator rather than restated.
        source: Absolute path of the config class's source file.
    """

    policy_id: str
    max_state_dim: int | None
    max_action_dim: int | None
    norm_mode: str
    camera_constraint: CameraConstraint
    structural_rules: tuple[str, ...]
    source: str


@dataclass(frozen=True)
class TrainingDefaults:
    """The ACT-shaped structural knobs read from a family's installed config.

    These are the values the structural rules read when a training request does
    not override them, so a policy evaluated at its own defaults never trips a
    structural rule that its shipped configuration would not (`10` FR-TRN-017 is a
    pre-check of a declared configuration, and the declared default is buildable).
    Only ACT reads the first four; the last two describe the dataset the request
    is checked against.

    Attributes:
        n_obs_steps: Observation steps the config ships with.
        n_action_steps: Action steps the config ships with.
        chunk_size: The action-chunk bound, falling back to `n_action_steps` when
            the family declares no chunk (only ACT's rule reads it).
        temporal_ensemble: Whether temporal ensembling is on by default
            (`temporal_ensemble_coeff` is not None).
        n_cameras: The default camera count a compatibility view assumes (one).
        has_state: Whether an `observation.state` feature is assumed present.
    """

    n_obs_steps: int
    n_action_steps: int
    chunk_size: int
    temporal_ensemble: bool
    n_cameras: int
    has_state: bool


def resolve_config_class(policy_id: str) -> Any:
    """Resolve a family's LeRobot config class through the installed registry.

    Importing the family's config module runs its registration decorator, then the
    class is looked up by name — no config class is named in this codebase, so the
    binding moves with the pin.

    Args:
        policy_id: A key of `POLICY_FAMILIES`.

    Returns:
        (type) The installed config dataclass for the family.

    Raises:
        KeyError: When `policy_id` is not a known family — an unknown family is a
            defect, not a silently uncapped policy.
    """
    module_name = _CONFIG_MODULES[policy_id]
    importlib.import_module(module_name)
    from lerobot.configs.policies import PreTrainedConfig

    return PreTrainedConfig.get_choice_class(policy_id)


def _field_default(config_class: Any, field_name: str) -> object:
    """Return a dataclass field's declared default, or a sentinel when absent.

    Args:
        config_class: The config dataclass to read.
        field_name: The field whose default is wanted.

    Returns:
        (object) The default value, `dataclasses.MISSING` when the field is
            required, or None when the field does not exist.
    """
    for field in dataclasses.fields(config_class):
        if field.name != field_name:
            continue
        if field.default is not dataclasses.MISSING:
            declared: object = field.default
            return declared
        if field.default_factory is not dataclasses.MISSING:
            produced: object = field.default_factory()
            return produced
        return dataclasses.MISSING
    return None


def _optional_int(value: object) -> int | None:
    """Coerce an introspected default to an int ceiling, or None when uncapped."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _int_or(value: object, fallback: int) -> int:
    """Coerce an introspected default to an int, using `fallback` when absent."""
    if isinstance(value, bool):
        return fallback
    if isinstance(value, int):
        return value
    return fallback


def _state_norm_mode(config_class: Any) -> str:
    """Read the STATE normalization mode name from the config's mapping.

    Args:
        config_class: The config dataclass to read.

    Returns:
        (str) The STATE `NormalizationMode` name (e.g. `MEAN_STD`, `QUANTILES`),
            or `UNKNOWN` when the config declares no state normalization.
    """
    mapping = _field_default(config_class, _NORMALIZATION_MAPPING_FIELD)
    if not isinstance(mapping, dict):
        return _NORM_MODE_UNKNOWN
    for key, mode in mapping.items():
        if str(key) != _STATE_NORM_KEY:
            continue
        name = getattr(mode, "name", None)
        return str(name) if name is not None else str(mode)
    return _NORM_MODE_UNKNOWN


def _applicable_rule_ids(
    policy_id: str, max_state_dim: int | None, max_action_dim: int | None
) -> tuple[str, ...]:
    """Probe the WP-0C-07 validator for the FR-TRN-017 rules that apply to a family.

    Rather than restate which rules gate on which `policy_type`, this feeds the
    validator a request that violates every condition at once and reports which
    codes it actually raises for the family — so `structural_rules` is derived from
    the canonical owner, not a second table that could drift from it.

    Args:
        policy_id: The policy family.
        max_state_dim: The introspected state ceiling (None when uncapped).
        max_action_dim: The introspected action ceiling (None when uncapped).

    Returns:
        (tuple[str, ...]) The applicable FR-TRN-017 sub-rule ids, in rule order.
    """
    over_state = (max_state_dim + 1) if max_state_dim is not None else 1
    over_action = (max_action_dim + 1) if max_action_dim is not None else 1
    spec = PolicySpec(
        policy_type=policy_id,
        n_obs_steps=2,
        n_action_steps=2,
        chunk_size=1,
        temporal_ensemble=True,
        max_state_dim=max_state_dim,
        max_action_dim=max_action_dim,
    )
    profile = DatasetProfile(
        state_dim=over_state,
        action_dim=over_action,
        n_cameras=2,
        has_state=False,
    )
    codes = {violation.code for violation in PolicyStructuralValidator().validate(spec, profile)}
    order = (
        PolicyConstraintCode.ACT_MULTIPLE_OBS_STEPS,
        PolicyConstraintCode.ACT_ACTION_STEPS_EXCEED_CHUNK,
        PolicyConstraintCode.TEMPORAL_ENSEMBLE_ACTION_STEPS,
        PolicyConstraintCode.DIFFUSION_MISSING_STATE,
        PolicyConstraintCode.VQBET_MULTIPLE_CAMERAS,
        PolicyConstraintCode.DIMENSION_CAP_EXCEEDED,
    )
    return tuple(RULE_ID_BY_CODE[code] for code in order if code in codes)


def capability_from_class(policy_id: str, config_class: Any) -> PolicyCapability:
    """Build a capability from an explicit config class.

    Separated from `introspect_capability` so a test can point it at a fabricated
    config class carrying a different ceiling and prove the value is READ, not
    copied — the positive half of the CG-4B-01f "moves with the pin" argument.

    Args:
        policy_id: The policy family the capability is for.
        config_class: The config dataclass to introspect.

    Returns:
        (PolicyCapability) The introspected capability.
    """
    max_state_dim = _optional_int(_field_default(config_class, _MAX_STATE_DIM_FIELD))
    max_action_dim = _optional_int(_field_default(config_class, _MAX_ACTION_DIM_FIELD))
    rules = _applicable_rule_ids(policy_id, max_state_dim, max_action_dim)
    camera = CameraConstraint.SINGLE if RULE_VQBET_CAMERAS in rules else CameraConstraint.NONE
    try:
        source = inspect.getsourcefile(config_class) or inspect.getfile(config_class)
    except TypeError:
        source = ""
    return PolicyCapability(
        policy_id=policy_id,
        max_state_dim=max_state_dim,
        max_action_dim=max_action_dim,
        norm_mode=_state_norm_mode(config_class),
        camera_constraint=camera,
        structural_rules=rules,
        source=source or "",
    )


def introspect_capability(policy_id: str) -> PolicyCapability:
    """Read a family's capability from its installed LeRobot config.

    Args:
        policy_id: A key of `POLICY_FAMILIES`.

    Returns:
        (PolicyCapability) The capability the installed config declares.
    """
    return capability_from_class(policy_id, resolve_config_class(policy_id))


def introspect_training_defaults(policy_id: str) -> TrainingDefaults:
    """Read the structural knobs a family ships with, for a default compatibility view.

    Args:
        policy_id: A key of `POLICY_FAMILIES`.

    Returns:
        (TrainingDefaults) The family's shipped knobs; only ACT reads the first
            four, and both dataset assumptions default to the single-camera state
            recording a training view starts from.
    """
    config_class = resolve_config_class(policy_id)
    n_action_steps = _int_or(_field_default(config_class, "n_action_steps"), 1)
    chunk_size = _int_or(_field_default(config_class, "chunk_size"), n_action_steps)
    temporal_coeff = _field_default(config_class, "temporal_ensemble_coeff")
    return TrainingDefaults(
        n_obs_steps=_int_or(_field_default(config_class, "n_obs_steps"), 1),
        n_action_steps=n_action_steps,
        chunk_size=chunk_size,
        temporal_ensemble=temporal_coeff is not None and temporal_coeff is not dataclasses.MISSING,
        n_cameras=1,
        has_state=True,
    )


def build_capability_registry() -> dict[str, PolicyCapability]:
    """Introspect every family in scope into a capability registry.

    Returns:
        (dict[str, PolicyCapability]) Family id to its introspected capability, in
            `POLICY_FAMILIES` order.
    """
    return {policy_id: introspect_capability(policy_id) for policy_id in POLICY_FAMILIES}


def wave0c_block_code(policy_id: str) -> str | None:
    """Return the Wave 0-C matrix's authored dimension block code for a family.

    Consumes `contracts/policy_compat.yaml` (the initial data) so the machine code
    the dimension block carries is the one Wave 0-C authored, not a fresh string
    invented here.

    Args:
        policy_id: The policy family.

    Returns:
        (str | None) The recorded `block_reason.code`, or None when the family is
            not one Wave 0-C recorded (the uncapped families, which carry no
            dimension block anyway).
    """
    for entry in load_registry():
        if entry.policy == policy_id:
            return entry.block_reason.code
    return None


def crosscheck_wave0c() -> tuple[str, ...]:
    """Prove live introspection still agrees with the Wave 0-C recorded ceilings.

    Wave 0-C recorded `max_state_dim`/`max_action_dim` for the families it covers;
    this re-reads them from the installed configs and reports any drift. A non-empty
    result is a rejected build (`10` FR-TRN-064 is `[확정]`), never a warning — the
    recorded matrix and the installed stack must not disagree silently.

    Returns:
        (tuple[str, ...]) One problem line per drift; empty when they agree.
    """
    problems: list[str] = []
    for entry in load_registry():
        if entry.policy not in POLICY_FAMILIES:
            continue
        capability = introspect_capability(entry.policy)
        if capability.max_state_dim != entry.max_state_dim:
            problems.append(
                f"{entry.policy}: Wave 0-C recorded max_state_dim {entry.max_state_dim} != "
                f"introspected {capability.max_state_dim}"
            )
        if capability.max_action_dim != entry.max_action_dim:
            problems.append(
                f"{entry.policy}: Wave 0-C recorded max_action_dim {entry.max_action_dim} != "
                f"introspected {capability.max_action_dim}"
            )
    return tuple(problems)
