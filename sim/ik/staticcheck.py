"""Static half of the FR-SIM-080 order contract and the fallback ban.

Two of this WP's guarantees are *absences*, and an absence can only be proven
statically — a runtime test shows the paths it happened to take, never the one a
future edit will add. So this is an AST scan, and it ships with a violation fixture
proving the scan bites.

- **Order (09 FR-SIM-080).** The only sanctioned way to reach a ``Kinematics`` is
  through ``sim.ik``'s ``OrderedIkBuild``, which forces the jnt_range override to
  run first. A consumer that constructs ``openarm_control``'s ``Kinematics`` (or its
  private ``_IKSolver``) directly has skipped that gate, so any reference to those
  symbols — by name, attribute, or symbol-import — from outside the owning tree is a
  finding. ``IKParams`` from the same module is not banned; importing it constructs
  nothing.
- **Unconstrained fallback (12 FR-SAF-016).** The upstream ``_IKSolver.solve``
  retries with ``limits=[]`` on ``NoSolutionFound`` (kinematics.py:220-231),
  discarding the soft limits silently. Banning direct use of ``_IKSolver`` is what
  keeps that hard-coded, uncontrollable fallback out of the command path; the
  adapter re-implements the solve loop precisely so the fallback becomes an opt-in,
  counted branch (``sim.ik.adapter``).

Scope is references — imports, calls, attribute and name uses — because that is how
a forbidden capability actually gets pulled in. The owning tree (``sim/ik``) is
exempt: it is where the sanctioned construction legitimately lives.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

# The raw openarm_control IK entry points a consumer must never touch directly. Both
# bypass the ordered builder; ``_IKSolver`` additionally carries the hard-coded
# unconstrained fallback. ``IKParams`` — a plain params dataclass in the same module —
# is deliberately not banned: importing it does not construct a solver.
BANNED_SYMBOLS: frozenset[str] = frozenset({"Kinematics", "_IKSolver"})

# The module the banned symbols live in; used only to catch a symbol-import of them.
KINEMATICS_MODULE = "openarm_control.kinematics"

# The tree that legitimately constructs Kinematics (the sanctioned, order-enforcing
# site). References here are not consumer bypasses and are exempt.
OWNER_PACKAGE = Path("sim") / "ik"

ORDER_RULE = "FR-SIM-080 order: reach Kinematics only through sim.ik.OrderedIkBuild"


@dataclass(frozen=True)
class StaticViolation:
    """A banned reference found by the scan.

    Attributes:
        path: File the reference was found in.
        line: 1-indexed line of the reference.
        symbol: The offending symbol or module string.
        rule: The absence that was violated, for the report line.
    """

    path: Path
    line: int
    symbol: str
    rule: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.rule}: {self.symbol}"


class _ReferenceVisitor(ast.NodeVisitor):
    """Collect references to the banned symbols and the banned import module."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.violations: list[StaticViolation] = []

    def _flag(self, symbol: str, line: int) -> None:
        self.violations.append(
            StaticViolation(path=self.path, line=line, symbol=symbol, rule=ORDER_RULE)
        )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        if node.module == KINEMATICS_MODULE:
            for alias in node.names:
                if alias.name in BANNED_SYMBOLS:
                    self._flag(alias.name, node.lineno)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802
        if node.attr in BANNED_SYMBOLS:
            self._flag(node.attr, node.lineno)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:  # noqa: N802
        if node.id in BANNED_SYMBOLS:
            self._flag(node.id, node.lineno)
        self.generic_visit(node)


def _is_owned(path: Path) -> bool:
    """Whether a file sits under the sim/ik owning tree.

    Args:
        path: File being scanned.

    Returns:
        (bool) True when the file is under ``sim/ik``.
    """
    parts = path.resolve().parts
    owner = OWNER_PACKAGE.parts
    return any(
        parts[index : index + len(owner)] == owner for index in range(len(parts) - len(owner) + 1)
    )


def scan_source(source: str, path: Path) -> list[StaticViolation]:
    """Scan one module's source for banned references.

    Args:
        source: Python source text.
        path: The path reported on findings.

    Returns:
        (list[StaticViolation]) Findings in the source, in source order.
    """
    visitor = _ReferenceVisitor(path)
    visitor.visit(ast.parse(source))
    return visitor.violations


def scan_tree(
    root: Path, exempt_owner: bool = True, exclude: Iterable[Path] = ()
) -> list[StaticViolation]:
    """Scan a directory tree for order/fallback violations.

    Args:
        root: Directory to scan recursively.
        exempt_owner: Whether files under ``sim/ik`` are skipped.
        exclude: Extra directories to skip (a fixture corpus passes its own).

    Returns:
        (list[StaticViolation]) Findings, sorted by path then line.
    """
    excluded = tuple(directory.resolve() for directory in exclude)
    violations: list[StaticViolation] = []
    for path in sorted(root.rglob("*.py")):
        resolved = path.resolve()
        if exempt_owner and _is_owned(path):
            continue
        if any(directory in resolved.parents or directory == resolved for directory in excluded):
            continue
        violations.extend(scan_source(path.read_text(encoding="utf-8"), path))
    return sorted(violations, key=lambda violation: (str(violation.path), violation.line))
