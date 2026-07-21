"""Load and validate `contracts/policy_compat.yaml` against reality.

The YAML is the declarative half of the matrix; this module is what keeps it from
drifting away from the installed stack. `load_registry` parses it, and
`verify_against_introspection` proves three things, each mirroring a check the ENV
band already makes on its own registries:

  * every recorded `max_state_dim` / `max_action_dim` equals the value the policy
    config actually declares (acceptance ⑪ — no hardcoded ceiling survives);
  * every `blocked_paths[].predicate` resolves to a real callable in
    `targets.guards` (the WP-ENV-02 acceptance ③ requirement, applied to the
    policy side);
  * every `supported_targets` entry is a real fleet target from
    `targets/matrix.yaml`.

A registry that passes all three is safe for the calculator to trust. Parsing is
stdlib + pyyaml; the introspection half imports the robot stack lazily, so the
document can be read for structure even where the stack is absent.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from targets.matrix import FLEET_TARGETS

REGISTRY_PATH = Path(__file__).resolve().parents[2] / "contracts" / "policy_compat.yaml"


@dataclass(frozen=True)
class BlockedPath:
    """A deploy path a policy is subject to, naming the guard that enforces it.

    Attributes:
        name: The path's identifier, e.g. `groot_sync_over_ceiling`.
        predicate: Dotted name of the `targets.guards` callable that decides it.
        rationale: The operator-facing reason, citing the FR it enforces.
    """

    name: str
    predicate: str
    rationale: str


@dataclass(frozen=True)
class BlockReason:
    """The two-field block reason `10` FR-TRN-064 requires: machine code + sentence.

    Attributes:
        code: The machine-readable block code.
        human: The operator-facing sentence.
    """

    code: str
    human: str


@dataclass(frozen=True)
class PolicyCompatEntry:
    """One policy's row in the compatibility registry.

    Attributes:
        policy: The policy family.
        config_module: Dotted module of the introspected config class.
        config_class: The config class whose ceilings this row mirrors.
        max_state_dim: Recorded `observation.state` ceiling.
        max_action_dim: Recorded `action` ceiling.
        supported_targets: Fleet targets this policy is offered on.
        blocked_paths: Guarded deploy paths this policy is subject to.
        block_reason: The dimension-block reason (code + sentence).
    """

    policy: str
    config_module: str
    config_class: str
    max_state_dim: int
    max_action_dim: int
    supported_targets: tuple[str, ...]
    blocked_paths: tuple[BlockedPath, ...]
    block_reason: BlockReason


def load_registry(path: Path = REGISTRY_PATH) -> tuple[PolicyCompatEntry, ...]:
    """Parse the policy compatibility registry.

    Args:
        path: Path to `contracts/policy_compat.yaml`.

    Returns:
        (tuple[PolicyCompatEntry, ...]) The declared policies, in document order.

    Raises:
        TypeError: When the document does not parse to a mapping with a policy list.
    """
    loaded: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict) or not isinstance(loaded.get("policies"), list):
        raise TypeError(f"{path} did not parse to a mapping with a 'policies' list")
    return tuple(_entry(row) for row in loaded["policies"])


def _entry(row: dict[str, Any]) -> PolicyCompatEntry:
    """Build one registry entry from a parsed row."""
    reason = row.get("block_reason") or {}
    return PolicyCompatEntry(
        policy=str(row["policy"]),
        config_module=str(row["config_module"]),
        config_class=str(row["config_class"]),
        max_state_dim=int(row["max_state_dim"]),
        max_action_dim=int(row["max_action_dim"]),
        supported_targets=tuple(str(t) for t in (row.get("supported_targets") or [])),
        blocked_paths=tuple(
            BlockedPath(
                name=str(bp.get("name", "")),
                predicate=str(bp.get("predicate", "")),
                rationale=str(bp.get("rationale", "")),
            )
            for bp in (row.get("blocked_paths") or [])
        ),
        block_reason=BlockReason(
            code=str(reason.get("code", "")),
            human=str(reason.get("human", "")).strip(),
        ),
    )


def _guard_resolves(dotted: str) -> bool:
    """Report whether a dotted name resolves to a callable guard.

    Args:
        dotted: `module.attr` path such as `targets.guards.sync_over_inference_ceiling`.

    Returns:
        (bool) True when the attribute exists and is callable.
    """
    module_name, _, attr = dotted.rpartition(".")
    if not module_name:
        return False
    try:
        module = importlib.import_module(module_name)
    except ImportError:
        return False
    return callable(getattr(module, attr, None))


def verify_against_introspection(
    entries: tuple[PolicyCompatEntry, ...],
) -> tuple[str, ...]:
    """Prove the registry matches the installed stack and names real guards/targets.

    Args:
        entries: The parsed registry.

    Returns:
        (tuple[str, ...]) One problem line per drift; empty when the registry is
            faithful. A non-empty result is a rejected registry, not a warning.
    """
    from backend.policy_matrix.caps import introspect_caps

    problems: list[str] = []
    for entry in entries:
        caps = introspect_caps(entry.policy)
        if caps.max_state_dim != entry.max_state_dim:
            problems.append(
                f"{entry.policy}: recorded max_state_dim {entry.max_state_dim} != "
                f"introspected {caps.max_state_dim}"
            )
        if caps.max_action_dim != entry.max_action_dim:
            problems.append(
                f"{entry.policy}: recorded max_action_dim {entry.max_action_dim} != "
                f"introspected {caps.max_action_dim}"
            )
        for target in entry.supported_targets:
            if target not in FLEET_TARGETS:
                problems.append(
                    f"{entry.policy}: supported target {target!r} is not a fleet target"
                )
        for path in entry.blocked_paths:
            if not _guard_resolves(path.predicate):
                problems.append(
                    f"{entry.policy}: blocked_path {path.name!r} predicate "
                    f"{path.predicate!r} does not resolve to a callable guard"
                )
    return tuple(problems)


def verify_env04_predicate() -> tuple[str, ...]:
    """Confirm the WP-ENV-04 `max_state_dim=32` fact still holds on the pin.

    Acceptance ⑪ ties the matrix's 32-dim ceiling to the value WP-ENV-04 guards,
    not to a literal. This runs that band's own predicate and reports its failure
    rather than re-deriving the fact — if the pin moved the default off 32, the
    ENV-04 predicate is where that surfaces first.

    Returns:
        (tuple[str, ...]) A single problem line when the ENV-04 predicate no longer
            holds; empty when it does.
    """
    from registry.env.upstream import resolve

    result = resolve("max_state_dim_default_32")()
    if result.ok:
        return ()
    return (
        f"WP-ENV-04 max_state_dim fact broken: expected {result.expected}, got {result.actual}",
    )
