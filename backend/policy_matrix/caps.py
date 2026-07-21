"""Introspected policy dimension ceilings and async-chunking defaults.

Acceptance ⑪ forbids a hardcoded `32`: the matrix's dimension axis must read its
ceiling from the value the pinned upstream actually declares, the same value the
WP-ENV-04 predicate (`registry.env.upstream.max_state_dim_default_32`) guards. So
this module imports each installed policy config class and reads its dataclass
default — `max_state_dim`, `max_action_dim`, `chunk_size` — rather than restating
any number in code. A pin that moved a ceiling changes what this returns, and the
registry cross-check (`backend.policy_matrix.registry`) turns that into a rejected
build instead of a silent drift.

The async-chunking defaults (`16` D-11) are read the same way, off LeRobot's
`RobotClientConfig`: `chunk_size_threshold` defaults to 0.5 and `actions_per_chunk`
carries no default at all (a required argument). Reading them here is what keeps
the stale documentation pair `50 / 0.7` out of this codebase — neither literal is
written down; both facts are introspected.

Imports of the robot stack sit inside the functions so the module is importable
for name resolution even where the stack is absent; the matrix itself only runs in
the heavy lane where LeRobot is installed.
"""

from __future__ import annotations

import dataclasses
import importlib
from dataclasses import dataclass

# Policy family -> (config module, config class). These are the four families the
# matrix ranks (`10` FR-TRN-064: SmolVLA/pi0/pi05 are the 32-dim-capped set, GR00T
# is the 132-dim one). The names are the installed LeRobot config classes; a family
# whose module or class is absent surfaces as an ImportError/AttributeError from
# `introspect_caps`, never as a fabricated ceiling.
POLICY_CONFIGS: dict[str, tuple[str, str]] = {
    "smolvla": ("lerobot.policies.smolvla.configuration_smolvla", "SmolVLAConfig"),
    "pi0": ("lerobot.policies.pi0.configuration_pi0", "PI0Config"),
    "pi05": ("lerobot.policies.pi05.configuration_pi05", "PI05Config"),
    "groot": ("lerobot.policies.groot.configuration_groot", "GrootConfig"),
}

_ASYNC_CONFIG_MODULE = "lerobot.async_inference.configs"
_ASYNC_CONFIG_CLASS = "RobotClientConfig"
_CHUNK_THRESHOLD_FIELD = "chunk_size_threshold"
_ACTIONS_PER_CHUNK_FIELD = "actions_per_chunk"

_FIELD_ABSENT = "<field-absent>"


@dataclass(frozen=True)
class PolicyCaps:
    """The dimension ceilings a policy family declares.

    Attributes:
        policy: The policy family, e.g. `smolvla` or `groot`.
        max_state_dim: The `observation.state` ceiling, or None when the policy
            declares none (uncapped).
        max_action_dim: The `action` ceiling, or None when uncapped.
        chunk_size: The policy's action-chunk width.
    """

    policy: str
    max_state_dim: int | None
    max_action_dim: int | None
    chunk_size: int | None


def _field_default(module_name: str, class_name: str, field_name: str) -> object:
    """Return a dataclass field's declared default, or a sentinel.

    Args:
        module_name: Dotted module to import.
        class_name: Dataclass attribute in that module.
        field_name: Field whose default is wanted.

    Returns:
        (object) The default value, `dataclasses.MISSING` when the field is
            required, or `"<field-absent>"` when the field does not exist.
    """
    module = importlib.import_module(module_name)
    cls = getattr(module, class_name)
    for field in dataclasses.fields(cls):
        if field.name != field_name:
            continue
        if field.default is not dataclasses.MISSING:
            declared: object = field.default
            return declared
        if field.default_factory is not dataclasses.MISSING:
            produced: object = field.default_factory()
            return produced
        return dataclasses.MISSING
    return _FIELD_ABSENT


def _optional_int(value: object) -> int | None:
    """Coerce an introspected default to an int ceiling, or None when uncapped.

    Args:
        value: A dataclass default read by `_field_default`.

    Returns:
        (int | None) The int value, or None when the field is absent/None.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def introspect_caps(policy: str) -> PolicyCaps:
    """Read a policy family's dimension ceilings from its installed config.

    Args:
        policy: A key of `POLICY_CONFIGS`.

    Returns:
        (PolicyCaps) The ceilings the installed config declares.

    Raises:
        KeyError: When `policy` is not a known family — an unknown family is a
            defect, not a silently uncapped policy.
    """
    module_name, class_name = POLICY_CONFIGS[policy]
    return PolicyCaps(
        policy=policy,
        max_state_dim=_optional_int(_field_default(module_name, class_name, "max_state_dim")),
        max_action_dim=_optional_int(_field_default(module_name, class_name, "max_action_dim")),
        chunk_size=_optional_int(_field_default(module_name, class_name, "chunk_size")),
    )


def async_chunk_size_threshold_default() -> float:
    """Return LeRobot's introspected `chunk_size_threshold` default (`16` D-11).

    Returns:
        (float) The dataclass default (0.5 on the current pin). Read, never
            written: this is what keeps the stale `0.7` literal out of the code.

    Raises:
        TypeError: When the introspected default is not a real number — a config
            that stopped declaring it must not be papered over with a guess.
    """
    default = _field_default(_ASYNC_CONFIG_MODULE, _ASYNC_CONFIG_CLASS, _CHUNK_THRESHOLD_FIELD)
    if isinstance(default, bool) or not isinstance(default, (int, float)):
        raise TypeError(f"{_ASYNC_CONFIG_CLASS}.{_CHUNK_THRESHOLD_FIELD} default is not numeric")
    return float(default)


def actions_per_chunk_is_required() -> bool:
    """Report whether `actions_per_chunk` has no default (`16` D-11).

    Returns:
        (bool) True when the installed `RobotClientConfig` leaves the field with
            no default — the ground truth the enforcer mirrors when it rejects an
            async plan that omits it.
    """
    default = _field_default(_ASYNC_CONFIG_MODULE, _ASYNC_CONFIG_CLASS, _ACTIONS_PER_CHUNK_FIELD)
    return default is dataclasses.MISSING
