"""Source-level invariants for the dry-run tree (acceptance ①, ④, ⑨).

Three structural bans, checked over the AST so a symbol in a comment or string
cannot trip them and a real use cannot hide behind formatting:

- **No fabricated transmission grant (④, `09` FR-SIM-033).** A ``TransmissionGrant``
  is the sole token authorising real transmission; it may be *constructed* only in
  ``interlock.py``, whose two sanctioned mints are the only bypass surface. A grant
  built anywhere else is a bypass path with no modal confirmation, so any
  ``TransmissionGrant(...)`` call outside ``interlock.py`` is a violation. Together
  with the runtime key-gated constructor, this leaves no implicit bypass.
- **No ``send_action`` on the twin path (⑨, `09` FR-SIM-099).** The digital twin is
  read-only; any reference to ``send_action`` in ``twin.py`` would be a command path,
  so zero such references is the invariant.
- **No CAN symbol (①, `09` FR-SIM-098).** No dry-run mode opens CAN. This delegates
  to the WP-0C-05 AST checker for the CAN/subprocess/in-tree-loop bans rather than
  re-implementing them, and runs it over the whole ``sim/dryrun`` tree.

``check_dryrun_tree`` runs all three over the package and returns every finding; the
acceptance test asserts zero over the real tree and non-zero over inline fixtures
that each plant one banned form, proving the checks bite.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from packages.lerobot_robot_openarm_dummy.staticcheck import check_source as check_can_bans

RULE_FABRICATED_GRANT = "fabricated-transmission-grant"
RULE_TWIN_SEND_ACTION = "twin-send-action"
RULE_CAN_SYMBOL = "dryrun-can-symbol"

# The one file allowed to construct a TransmissionGrant.
_INTERLOCK_FILENAME = "interlock.py"
# The read-only twin path that must never reference a command symbol.
_TWIN_FILENAME = "twin.py"
_GRANT_SYMBOL = "TransmissionGrant"
_COMMAND_SYMBOL = "send_action"


@dataclass(frozen=True)
class StaticFinding:
    """One dry-run static-checker finding.

    Attributes:
        rule: Which ban fired.
        module: Path label of the checked source.
        line: 1-indexed source line.
        message: Human-readable description naming the actual violation.
    """

    rule: str
    module: str
    line: int
    message: str


def _construction_calls(tree: ast.AST, symbol: str) -> list[int]:
    """Return the lines where ``symbol(...)`` is called (attribute or bare name)."""
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (
            isinstance(func, ast.Name)
            and func.id == symbol
            or isinstance(func, ast.Attribute)
            and func.attr == symbol
        ):
            lines.append(node.lineno)
    return lines


def check_grant_construction(source: str, module: str) -> list[StaticFinding]:
    """Flag any ``TransmissionGrant`` construction outside ``interlock.py`` (④)."""
    if Path(module).name == _INTERLOCK_FILENAME:
        return []
    tree = ast.parse(source)
    return [
        StaticFinding(
            rule=RULE_FABRICATED_GRANT,
            module=module,
            line=line,
            message=(
                "constructs a TransmissionGrant outside interlock.py — a grant "
                "fabricated here is a bypass with no modal confirm (09 FR-SIM-033)"
            ),
        )
        for line in _construction_calls(tree, _GRANT_SYMBOL)
    ]


def check_twin_no_send_action(source: str, module: str) -> list[StaticFinding]:
    """Flag any ``send_action`` reference in ``twin.py`` (⑨)."""
    if Path(module).name != _TWIN_FILENAME:
        return []
    tree = ast.parse(source)
    findings: list[StaticFinding] = []
    for node in ast.walk(tree):
        hit = (isinstance(node, ast.Attribute) and node.attr == _COMMAND_SYMBOL) or (
            isinstance(node, ast.Name) and node.id == _COMMAND_SYMBOL
        )
        if hit:
            findings.append(
                StaticFinding(
                    rule=RULE_TWIN_SEND_ACTION,
                    module=module,
                    line=node.lineno,
                    message="references send_action on the read-only twin path (09 FR-SIM-099)",
                )
            )
    return findings


def check_no_can(source: str, module: str) -> list[StaticFinding]:
    """Flag CAN symbols via the WP-0C-05 AST checker (①)."""
    return [
        StaticFinding(
            rule=RULE_CAN_SYMBOL,
            module=module,
            line=violation.line,
            message=violation.message,
        )
        for violation in check_can_bans(source, module=module)
        if violation.rule == "can-symbol"
    ]


def check_dryrun_tree(root: Path) -> tuple[StaticFinding, ...]:
    """Run all three dry-run source bans over every ``.py`` file under ``root``.

    Args:
        root: The ``sim/dryrun`` package directory.

    Returns:
        (tuple[StaticFinding, ...]) Every finding, in file then line order.
    """
    findings: list[StaticFinding] = []
    for path in sorted(root.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        module = str(path)
        findings.extend(check_grant_construction(source, module))
        findings.extend(check_twin_no_send_action(source, module))
        findings.extend(check_no_can(source, module))
    return tuple(findings)
