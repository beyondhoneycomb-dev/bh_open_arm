"""Static (compile-stage) proof of the two Freedrive absences the wire path depends on.

Two acceptance gates are stated as things that must **not** exist, and the only honest way to
check an absence is statically — a runtime test shows only the paths it happened to run.

- Acceptance V — **the bypass path passes the single gateway (I-4).** Freedrive releases the
  position path's tau-zero constraint, but it must still route through the one enforcement
  gateway, never around it to the bus. This is proved two ways: the reused actuation scans find
  zero reaches for the CAN handle from the Freedrive tree, and a positive scan confirms the
  command path references the gateway's ``submit``. Releasing a constraint through the sanctioned
  gateway is not opening a second write path; this proves none was opened.
- Acceptance II — **no toggle and no auto-hold implementation.** FR-MAN-029 admits only
  hold-to-activate. A function or method whose name declares a toggle or an auto-hold is a
  finding, so the absence is checked at build time rather than assumed from a reading of ``tick``.

Scope for the toggle scan is definition names and references, because that is how such an
implementation would actually appear; string constants that merely name the concept in prose are
not definitions and are not flagged.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable
from pathlib import Path

from backend.actuation.staticcheck import (
    StaticViolation,
    find_disable_torque,
    find_producer_can_access,
)

# The gateway symbols a Freedrive command path must reference to prove it routes through the
# single enforcement point rather than around it.
GATEWAY_TYPE_SYMBOL = "ActuationGateway"
GATEWAY_SUBMIT_SYMBOL = "submit"

# Name fragments that mark a toggle or auto-hold implementation, banned by FR-MAN-029.
BANNED_ACTIVATION_FRAGMENTS: tuple[str, ...] = (
    "toggle",
    "auto_hold",
    "autohold",
    "auto_activate",
    "auto_resume",
)

_TOGGLE_RULE = "toggle or auto-hold implementation (FR-MAN-029 admits only hold-to-activate)"


class _ActivationVisitor(ast.NodeVisitor):
    """Flag function/method definitions whose name declares a banned activation mode."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.violations: list[StaticViolation] = []

    def _check_def(self, name: str, line: int) -> None:
        """Flag a definition whose name contains a banned activation fragment.

        Args:
            name: The definition's name.
            line: 1-indexed source line.
        """
        lowered = name.lower()
        for fragment in BANNED_ACTIVATION_FRAGMENTS:
            if fragment in lowered:
                self.violations.append(
                    StaticViolation(path=self.path, line=line, symbol=name, rule=_TOGGLE_RULE)
                )
                return

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802  (ast visitor naming)
        self._check_def(node.name, node.lineno)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self._check_def(node.name, node.lineno)
        self.generic_visit(node)


def find_toggle_or_autohold(root: Path) -> list[StaticViolation]:
    """Find any toggle or auto-hold definition under a tree (acceptance II).

    This checker's own file is exempt: it names the banned fragments as data and logic, the same
    self-exemption the deprecated-symbol scans use for their defining package.

    Args:
        root: Directory to scan recursively.

    Returns:
        (list[StaticViolation]) Offending definitions, sorted by path and line.
    """
    checker = Path(__file__).resolve()
    violations: list[StaticViolation] = []
    for path in sorted(root.rglob("*.py")):
        if path.resolve() == checker:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        visitor = _ActivationVisitor(path)
        visitor.visit(tree)
        violations.extend(visitor.violations)
    return sorted(violations, key=lambda item: (str(item.path), item.line))


def references_single_gateway(root: Path) -> bool:
    """Report whether the tree routes its command through the single gateway (positive V check).

    Args:
        root: Directory to scan recursively.

    Returns:
        (bool) True when some file references both the gateway type and its ``submit`` entry.
    """
    saw_type = False
    saw_submit = False
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == GATEWAY_TYPE_SYMBOL:
                saw_type = True
            elif isinstance(node, ast.Attribute) and node.attr == GATEWAY_SUBMIT_SYMBOL:
                saw_submit = True
    return saw_type and saw_submit


def scan_freedrive_single_gateway(
    root: Path, exclude: Iterable[Path] = ()
) -> list[StaticViolation]:
    """Prove the Freedrive path passes the single gateway and reaches no CAN handle (V).

    Combines the reused actuation absence scans — no producer reaches the CAN handle, no torque
    cut appears — with the positive requirement that the command path references the gateway. A
    tree that reaches the bus directly, or that never routes through the gateway, is a finding.

    Args:
        root: The Freedrive tree to scan.
        exclude: Directories to skip explicitly.

    Returns:
        (list[StaticViolation]) All violations, empty when the bypass is honest.
    """
    violations = list(find_producer_can_access(root, exclude))
    violations.extend(find_disable_torque(root, exclude))
    if not references_single_gateway(root):
        violations.append(
            StaticViolation(
                path=root,
                line=0,
                symbol=f"{GATEWAY_TYPE_SYMBOL}.{GATEWAY_SUBMIT_SYMBOL}",
                rule="Freedrive command path does not route through the single gateway (I-4)",
            )
        )
    return sorted(violations, key=lambda item: (str(item.path), item.line))
