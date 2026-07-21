"""Static rejection of hard-coded qpos/dof indices (acceptance ③).

The contract of this WP is that joint indices are resolved *by name* at runtime
(``mujoco.mj_name2id`` -> ``jnt_qposadr`` / ``jnt_dofadr``), never written as
literals. A literal index into a MuJoCo state array is a latent bug: it is correct
only for one qpos layout and reads the wrong joint the moment the layout shifts —
exactly the shift ``sim.fkik.shuffle`` induces. A runtime test cannot prove this
absence, because it only exercises the layouts it happens to load; the guarantee has
to be static. So this is an AST scan, and it ships with a violation fixture proving
the scan bites and a clean fixture proving it does not over-reach.

A finding is a subscript of a state array (``qpos`` / ``qvel`` / ``qacc`` / ``ctrl``,
whether bare or as ``data.qpos``) whose index is an integer literal or a slice with
any integer-literal bound: ``data.qpos[7]``, ``qpos[0:7]``, ``ctrl[:8]``. Indexing
the *resolution tables* is deliberately not flagged — ``model.jnt_qposadr[jid]`` is
how a name-resolved index is looked up, and its subscripted array is not a state
array. Indexing a state array by a *variable* (``qpos[adr]``) is the sanctioned path
and is not flagged either; the sin is the literal, not the subscript.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

# MuJoCo per-step state arrays. A literal index into one of these binds code to a
# specific qpos/dof/actuator layout. The resolution tables (``jnt_qposadr`` etc.)
# are intentionally absent: indexing them by a name-resolved id is the correct path.
STATE_ARRAYS: frozenset[str] = frozenset({"qpos", "qvel", "qacc", "ctrl"})

INDEX_RULE = "index joints by name (mujoco.mj_name2id), never by a hard-coded literal"

# The tree that owns the FK<->IK harness; its own code must resolve by name, so it is
# scanned rather than exempted (dogfooding the rule on the checker's own package).
OWNER_PACKAGE = Path("sim") / "fkik"


@dataclass(frozen=True)
class HardcodedIndex:
    """A literal index into a MuJoCo state array found by the scan.

    Attributes:
        path: File the reference was found in.
        line: 1-indexed line of the subscript.
        array: The state array being indexed (``qpos``, ``ctrl``, ...).
        index: The offending index text, for the report line.
        rule: The rule the reference violates.
    """

    path: Path
    line: int
    array: str
    index: str
    rule: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.rule}: {self.array}[{self.index}]"


def _state_array_name(node: ast.expr) -> str | None:
    """Return the state-array name a subscript targets, or None if it is not one.

    Args:
        node: The value expression of a ``Subscript``.

    Returns:
        (str | None) ``qpos`` / ``qvel`` / ``qacc`` / ``ctrl`` when the target is one
        of them (bare or as an attribute like ``data.qpos``), else None.
    """
    if isinstance(node, ast.Name) and node.id in STATE_ARRAYS:
        return node.id
    if isinstance(node, ast.Attribute) and node.attr in STATE_ARRAYS:
        return node.attr
    return None


def _literal_int(node: ast.expr | None) -> int | None:
    """Return the integer value of a literal expression, or None if not a literal int.

    Handles a bare ``Constant`` and a unary +/- on one, so ``7`` and ``-1`` both read
    as literals while ``True`` (a bool constant) does not.

    Args:
        node: An index or slice-bound expression, possibly None.

    Returns:
        (int | None) The literal integer, or None.
    """
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, int)
        and not isinstance(node.value, bool)
    ):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        inner = _literal_int(node.operand)
        if inner is not None:
            return -inner if isinstance(node.op, ast.USub) else inner
    return None


def _hardcoded_index_text(slice_node: ast.expr) -> str | None:
    """Return a rendering of a hard-coded index/slice, or None when it is not one.

    Args:
        slice_node: The ``slice`` field of a ``Subscript``.

    Returns:
        (str | None) A short ``7`` / ``0:7`` / ``:8`` rendering when at least one
        bound is an integer literal, else None.
    """
    literal = _literal_int(slice_node)
    if literal is not None:
        return str(literal)
    if isinstance(slice_node, ast.Slice):
        bounds = (slice_node.lower, slice_node.upper, slice_node.step)
        if any(_literal_int(bound) is not None for bound in bounds):
            parts = ["" if bound is None else _bound_text(bound) for bound in bounds[:2]]
            rendered = ":".join(parts)
            if slice_node.step is not None:
                rendered += ":" + _bound_text(slice_node.step)
            return rendered
    return None


def _bound_text(node: ast.expr) -> str:
    """Render a slice bound as its literal value or a placeholder for a non-literal."""
    literal = _literal_int(node)
    return str(literal) if literal is not None else "?"


class _IndexVisitor(ast.NodeVisitor):
    """Collect literal indices into MuJoCo state arrays."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.violations: list[HardcodedIndex] = []

    def visit_Subscript(self, node: ast.Subscript) -> None:  # noqa: N802
        array = _state_array_name(node.value)
        if array is not None:
            index = _hardcoded_index_text(node.slice)
            if index is not None:
                self.violations.append(
                    HardcodedIndex(
                        path=self.path,
                        line=node.lineno,
                        array=array,
                        index=index,
                        rule=INDEX_RULE,
                    )
                )
        self.generic_visit(node)


def scan_source(source: str, path: Path) -> list[HardcodedIndex]:
    """Scan one module's source for hard-coded state-array indices.

    Args:
        source: Python source text.
        path: The path reported on findings.

    Returns:
        (list[HardcodedIndex]) Findings in source order.
    """
    visitor = _IndexVisitor(path)
    visitor.visit(ast.parse(source))
    return visitor.violations


def scan_tree(root: Path, exclude: Iterable[Path] = ()) -> list[HardcodedIndex]:
    """Scan a directory tree for hard-coded state-array indices.

    Args:
        root: Directory to scan recursively.
        exclude: Directories to skip (a fixture corpus passes its own).

    Returns:
        (list[HardcodedIndex]) Findings, sorted by path then line.
    """
    excluded = tuple(directory.resolve() for directory in exclude)
    violations: list[HardcodedIndex] = []
    for path in sorted(root.rglob("*.py")):
        resolved = path.resolve()
        if any(directory in resolved.parents or directory == resolved for directory in excluded):
            continue
        violations.extend(scan_source(path.read_text(encoding="utf-8"), path))
    return sorted(violations, key=lambda violation: (str(violation.path), violation.line))
