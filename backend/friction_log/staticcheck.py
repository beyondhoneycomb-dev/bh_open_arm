"""The load-bearing no-transmit / no-observe scans for the logger path (WP-2B-05).

This is the safety barrier the whole friction wave stands behind (WP-2B-06/07 are its
downstream). Two acceptance items are stated as things that must NOT be reachable, and
the only honest way to check an absence is statically — a runtime test shows only the
paths it happened to exercise:

- **Acceptance ① — zero CAN transmit on the logger path.** No CAN-writer symbol, no
  socket send, no `robot.bus` handle. A transmit here is a second writer on the bus
  (I-1) and drops a brakeless arm, so a finding is FAIL_BLOCKING.
- **Acceptance ⑥ — zero `get_observation` on the pattern-A tick path.** Pattern A is a
  tick condition: the scheduler reads state from the MIT response, not a per-cycle
  observation poll. A `get_observation` reference breaks the condition.

Both scans work over the AST, so a symbol in a comment or a string cannot trip them and
a real use cannot hide behind formatting. `check_source` runs on one source string —
which is what the tests use to prove the scan bites — and `scan_tree` runs it over the
real package, which the acceptance test asserts is clean.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

RULE_CAN_TRANSMIT = "logger-can-transmit"
RULE_GET_OBSERVATION = "logger-get-observation"

# Symbols that put torque on the bus: the CAN-writer handle and its write method, and the
# socket send family. A logger naming any of these is reaching to become a second writer.
_TRANSMIT_SYMBOLS: frozenset[str] = frozenset(
    {
        "mit_control_batch",
        "_mit_control_batch",
        "CanWriter",
        "FakeCanWriter",
        "BusCanWriter",
        "send",
        "sendall",
        "sendto",
        "sendmsg",
    }
)
# Importing the CAN-writer module is reaching for the handle even without naming a method.
_TRANSMIT_MODULE = "backend.actuation.can_writer"
# `robot.bus` is the direct bus handle the tap must never take (05 §6.3.1).
_BUS_ATTR = "bus"
# The poll pattern A must not use: it reads state from the MIT response, not an
# observation fetched every cycle (PG-CAN-001 tick condition).
_OBSERVATION_SYMBOL = "get_observation"


@dataclass(frozen=True)
class Finding:
    """A forbidden reference found by a scan.

    Attributes:
        rule: Which absence was violated (`RULE_CAN_TRANSMIT` or `RULE_GET_OBSERVATION`).
        module: Path label of the checked source.
        line: 1-indexed source line of the reference.
        symbol: The offending symbol or module.
    """

    rule: str
    module: str
    line: int
    symbol: str

    def __str__(self) -> str:
        return f"{self.module}:{self.line}: {self.rule}: {self.symbol}"


def _import_hits(node: ast.Import | ast.ImportFrom, module: str, line: int) -> list[Finding]:
    """Return findings for an import of the forbidden CAN-writer module."""
    names: list[str] = []
    if isinstance(node, ast.Import):
        names = [alias.name for alias in node.names]
    elif node.module is not None:
        names = [node.module]
    return [
        Finding(RULE_CAN_TRANSMIT, module, line, name)
        for name in names
        if name == _TRANSMIT_MODULE or name.startswith(_TRANSMIT_MODULE + ".")
    ]


def check_source(source: str, module: str) -> list[Finding]:
    """Scan one source string for CAN transmit (①) and `get_observation` (⑥) references.

    Args:
        source: Python source text.
        module: Path label for the findings.

    Returns:
        (list[Finding]) Every forbidden reference, in source order.
    """
    tree = ast.parse(source)
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            findings.extend(_import_hits(node, module, node.lineno))
        elif isinstance(node, ast.Attribute):
            if node.attr in _TRANSMIT_SYMBOLS or node.attr == _BUS_ATTR:
                findings.append(Finding(RULE_CAN_TRANSMIT, module, node.lineno, node.attr))
            elif node.attr == _OBSERVATION_SYMBOL:
                findings.append(Finding(RULE_GET_OBSERVATION, module, node.lineno, node.attr))
        elif isinstance(node, ast.Name):
            if node.id in _TRANSMIT_SYMBOLS:
                findings.append(Finding(RULE_CAN_TRANSMIT, module, node.lineno, node.id))
            elif node.id == _OBSERVATION_SYMBOL:
                findings.append(Finding(RULE_GET_OBSERVATION, module, node.lineno, node.id))
    return findings


def scan_tree(root: Path, exclude: tuple[Path, ...] = ()) -> tuple[Finding, ...]:
    """Run both source bans over every `.py` file under `root`.

    Args:
        root: Directory to scan recursively.
        exclude: Directories to skip (a fixture corpus passes its own).

    Returns:
        (tuple[Finding, ...]) Every finding, in file then source order.
    """
    excluded = tuple(directory.resolve() for directory in exclude)
    findings: list[Finding] = []
    for path in sorted(root.rglob("*.py")):
        resolved = path.resolve()
        if any(directory in resolved.parents for directory in excluded):
            continue
        relative_parents = path.relative_to(root).parts[:-1]
        if any(part.startswith(".") or part == "__pycache__" for part in relative_parents):
            continue
        findings.extend(check_source(path.read_text(encoding="utf-8"), str(path)))
    return tuple(findings)
