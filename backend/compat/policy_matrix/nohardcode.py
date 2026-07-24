"""The CG-4B-01f static check: no hardcoded capability constant in the engine.

FR-TRN-064 is `[확정]` and the failure it guards against is silent: a `max_state_dim`
copied into a constant reads correctly today and lies the day a pin moves the
ceiling, and nothing observes the lie until a 48-dim dataset truncates inside
LeRobot. So the engine must READ every ceiling from the installed config, and this
scanner proves it did — it walks the engine's own source and rejects any integer
literal equal to a live capability ceiling.

The forbidden set is itself introspected, not written down: it is the set of
ceilings the installed configs currently declare (32 and 132 on this pin). A build
where the caps move re-derives the forbidden set, so the check tracks the pin
rather than pinning the check. The scanner is the runtime half of CG-4B-01f; a
fixture snippet carrying `max_state_dim = 32` is the positive control that proves
it bites rather than passing vacuously.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from backend.compat.policy_matrix.capability import build_capability_registry

PACKAGE_ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class HardcodedLiteral:
    """A capability-valued integer literal found in engine source.

    Attributes:
        path: The file the literal was found in.
        line: 1-indexed line of the literal.
        value: The literal's integer value — one of the live capability ceilings.
    """

    path: str
    line: int
    value: int


def forbidden_capability_values() -> frozenset[int]:
    """Return the live capability ceilings a literal must not restate.

    Derived from the installed configs so the forbidden set moves with the pin: the
    values are exactly the non-null `max_state_dim`/`max_action_dim` the capability
    registry introspected, never a written-down list.

    Returns:
        (frozenset[int]) The distinct introspected ceiling values.
    """
    values: set[int] = set()
    for capability in build_capability_registry().values():
        if capability.max_state_dim is not None:
            values.add(capability.max_state_dim)
        if capability.max_action_dim is not None:
            values.add(capability.max_action_dim)
    return frozenset(values)


def scan_source(
    source: str, forbidden: frozenset[int], path: str = "<string>"
) -> list[HardcodedLiteral]:
    """Scan one Python source for integer literals equal to a forbidden ceiling.

    Args:
        source: The Python source text.
        forbidden: The capability ceilings a literal must not restate.
        path: A label for the source, used in the finding.

    Returns:
        (list[HardcodedLiteral]) One finding per offending literal, in source order.
    """
    findings: list[HardcodedLiteral] = []
    tree = ast.parse(source, filename=path)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant):
            continue
        value = node.value
        if isinstance(value, bool) or not isinstance(value, int):
            continue
        if value in forbidden:
            findings.append(HardcodedLiteral(path=path, line=node.lineno, value=value))
    return findings


def scan_package(
    root: Path | None = None, forbidden: frozenset[int] | None = None
) -> list[HardcodedLiteral]:
    """Scan every engine source file for hardcoded capability constants.

    Args:
        root: The package directory to scan; defaults to this package.
        forbidden: The forbidden ceilings; defaults to the introspected live set.

    Returns:
        (list[HardcodedLiteral]) Every offending literal across the package, empty
            when the engine holds no copied ceiling.
    """
    scan_root = root if root is not None else PACKAGE_ROOT
    values = forbidden if forbidden is not None else forbidden_capability_values()
    findings: list[HardcodedLiteral] = []
    for source_file in sorted(scan_root.rglob("*.py")):
        rel = source_file.relative_to(scan_root).as_posix()
        findings.extend(
            scan_source(source_file.read_text(encoding="utf-8"), values, path=rel)
        )
    return findings
