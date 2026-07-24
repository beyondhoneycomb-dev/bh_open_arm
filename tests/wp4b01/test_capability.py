"""WP-4B-01 capability registry: values are READ from the installed config.

These cover the source-derivation half of the acceptance gates: the ceilings,
normalization mode, camera constraint and structural rules a policy imposes are
introspected off the installed LeRobot config, carry that config's source file as
provenance (FR-TRN-004), and agree with the Wave 0-C recorded matrix.
"""

from __future__ import annotations

import dataclasses

from backend.compat.policy_matrix import (
    POLICY_FAMILIES,
    CameraConstraint,
    build_capability_registry,
    capability_from_class,
    crosscheck_wave0c,
    introspect_capability,
    resolve_config_class,
)
from backend.compat.policy_matrix.capability import (
    RULE_ACT_ACTION_STEPS,
    RULE_ACT_OBS_STEPS,
    RULE_DIFFUSION_STATE,
    RULE_DIMENSION_CAP,
    RULE_TEMPORAL_ENSEMBLE,
    RULE_VQBET_CAMERAS,
)

_CAPPED_FAMILIES = ("smolvla", "pi0", "pi05")


def test_capped_ceilings_match_the_installed_config() -> None:
    """Each 32-capped family reports the ceiling its config actually declares."""
    for policy_id in _CAPPED_FAMILIES:
        config_class = resolve_config_class(policy_id)
        declared = next(
            field.default
            for field in dataclasses.fields(config_class)
            if field.name == "max_state_dim"
        )
        capability = introspect_capability(policy_id)
        assert capability.max_state_dim == declared
        assert capability.max_action_dim == declared


def test_groot_ceiling_clears_bimanual() -> None:
    """GR00T's introspected ceiling is its declared 132, which clears 48."""
    config_class = resolve_config_class("groot")
    declared = next(
        field.default for field in dataclasses.fields(config_class) if field.name == "max_state_dim"
    )
    capability = introspect_capability("groot")
    assert capability.max_state_dim == declared
    assert capability.max_state_dim is not None
    assert capability.max_state_dim > 48


def test_uncapped_families_report_no_ceiling() -> None:
    """ACT/Diffusion/VQ-BeT declare no dimension cap, so the capability is None."""
    for policy_id in ("act", "diffusion", "vqbet"):
        capability = introspect_capability(policy_id)
        assert capability.max_state_dim is None
        assert capability.max_action_dim is None


def test_capability_is_read_not_copied() -> None:
    """A fabricated config with a moved ceiling changes the capability (CG-4B-01f).

    This is the positive proof that the value flows from the config class: point
    the introspector at a class carrying `max_state_dim=777` and the capability
    reports 777, not a copied 32.
    """

    @dataclasses.dataclass
    class MovedConfig:
        max_state_dim: int = 777
        max_action_dim: int = 777
        normalization_mapping: dict[str, str] = dataclasses.field(
            default_factory=lambda: {"STATE": "MEAN_STD"}
        )

    capability = capability_from_class("smolvla", MovedConfig)
    assert capability.max_state_dim == 777
    assert capability.max_action_dim == 777


def test_norm_mode_is_source_derived() -> None:
    """The STATE normalization mode is read from the config (FR-TRN-020 for pi05)."""
    assert introspect_capability("pi05").norm_mode == "QUANTILES"
    assert introspect_capability("smolvla").norm_mode == "MEAN_STD"


def test_camera_constraint_marks_vqbet_single() -> None:
    """Only VQ-BeT carries the single-camera constraint; the rest carry none."""
    assert introspect_capability("vqbet").camera_constraint is CameraConstraint.SINGLE
    for policy_id in ("smolvla", "pi0", "pi05", "act", "diffusion", "groot"):
        assert introspect_capability(policy_id).camera_constraint is CameraConstraint.NONE


def test_structural_rules_are_probed_per_family() -> None:
    """`structural_rules` reports the FR-TRN-017 rules the validator applies."""
    assert set(introspect_capability("act").structural_rules) == {
        RULE_ACT_OBS_STEPS,
        RULE_ACT_ACTION_STEPS,
        RULE_TEMPORAL_ENSEMBLE,
    }
    assert introspect_capability("diffusion").structural_rules == (RULE_DIFFUSION_STATE,)
    assert introspect_capability("vqbet").structural_rules == (RULE_VQBET_CAMERAS,)
    for policy_id in (*_CAPPED_FAMILIES, "groot"):
        assert introspect_capability(policy_id).structural_rules == (RULE_DIMENSION_CAP,)


def test_source_points_at_the_config_file() -> None:
    """The provenance is the family's own config source file (FR-TRN-004)."""
    assert introspect_capability("smolvla").source.endswith("configuration_smolvla.py")
    assert introspect_capability("groot").source.endswith("configuration_groot.py")


def test_registry_covers_every_family_in_scope() -> None:
    """The registry introspects exactly the families WP-4B-01 ranks."""
    registry = build_capability_registry()
    assert tuple(registry) == POLICY_FAMILIES


def test_crosscheck_against_wave0c_is_clean() -> None:
    """Live introspection agrees with the Wave 0-C recorded ceilings (no drift)."""
    assert crosscheck_wave0c() == ()
