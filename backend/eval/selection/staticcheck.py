"""Static (compile-stage) proof of two absences the selection policy depends on.

Two of the WP-4C-06 acceptance gates are stated as things that must **not** be
reachable, and the only honest way to check an absence is statically — a runtime
test shows only the paths it happened to exercise. So these are AST scans, and each
ships with a violation fixture proving the scan actually bites (the WP-BOOT-03
discipline the sibling `backend/*/staticcheck.py` modules follow).

- **CG-4C-06a — an offline metric is never a sort or selection key** (`FR-INF-062`).
  `val_loss` and `action_mse` are legitimate to STORE and to DISPLAY (`02c` §3.6:
  "표시하되 정렬 불가"), so the scan does not ban the symbols outright — it flags them
  only where they enter an ordering: a `sorted`/`min`/`max`/`.sort` call, a
  comparison operator, or a selection sink. Reading one to format it into a report
  string is none of those and stays legal.
- **CG-4C-06c — no checkpoint is auto-deleted on an offline-metric criterion**
  (`FR-TRN-042`). The scan flags an offline metric flowing into any delete/prune
  sink. This package owns no deletion at all, so the owned tree scans clean; the
  scan exists to keep a later edit from quietly introducing a loss-based auto-delete.

Scope is the reference contexts that constitute a decision, not every mention, which
is why the display path in `scorecard.render` is not a finding.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from backend.eval.selection.constants import (
    DELETE_SINKS,
    OFFLINE_METRIC_FIELDS,
    RULE_NO_LOSS_AUTO_DELETE,
    RULE_NO_OFFLINE_SORT,
    SELECT_SINKS,
    SORT_CALLS,
    SORT_METHODS,
)


@dataclass(frozen=True)
class StaticViolation:
    """A forbidden offline-metric reference found by a scan.

    Attributes:
        path: File the reference was found in.
        line: 1-indexed line of the offending construct.
        symbol: The offline metric name(s) that reached a decision context.
        rule: Which absence was violated, for the report line.
    """

    path: Path
    line: int
    symbol: str
    rule: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.rule}: {self.symbol}"


def _callee_name(node: ast.expr) -> str:
    """Return the simple name a call targets (`f(...)` or `obj.f(...)`)."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _is_offline_expr(node: ast.AST) -> bool:
    """Whether one node reads an offline metric (`.val_loss` / `val_loss` / `"val_loss"`)."""
    if isinstance(node, ast.Attribute):
        return node.attr in OFFLINE_METRIC_FIELDS
    if isinstance(node, ast.Name):
        return node.id in OFFLINE_METRIC_FIELDS
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str) and node.value in OFFLINE_METRIC_FIELDS
    if isinstance(node, ast.Subscript):
        key = node.slice
        return (
            isinstance(key, ast.Constant)
            and isinstance(key.value, str)
            and key.value in OFFLINE_METRIC_FIELDS
        )
    return False


def _offline_names_in(node: ast.AST) -> tuple[str, ...]:
    """Return the offline-metric names referenced anywhere in a node's subtree."""
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Attribute) and child.attr in OFFLINE_METRIC_FIELDS:
            names.add(child.attr)
        elif isinstance(child, ast.Name) and child.id in OFFLINE_METRIC_FIELDS:
            names.add(child.id)
        elif (
            isinstance(child, ast.Constant)
            and isinstance(child.value, str)
            and child.value in OFFLINE_METRIC_FIELDS
        ):
            names.add(child.value)
        elif isinstance(child, ast.Subscript) and _is_offline_expr(child):
            key = child.slice
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                names.add(key.value)
    return tuple(sorted(names))


def _is_sort_call(node: ast.Call) -> bool:
    """Whether a call is a sort/min/max ordering or a `.sort` method call."""
    if _callee_name(node.func) in SORT_CALLS:
        return True
    return isinstance(node.func, ast.Attribute) and node.func.attr in SORT_METHODS


def scan_source(path: Path, source: str) -> list[StaticViolation]:
    """Scan one module's source for an offline metric reaching a decision context.

    Args:
        path: The module path, for the violation record.
        source: The module source text.

    Returns:
        (list[StaticViolation]) Findings in source order, deduplicated per
            (line, rule).
    """
    tree = ast.parse(source, filename=str(path))
    found: dict[tuple[int, str], StaticViolation] = {}

    def flag(node: ast.AST, rule: str) -> None:
        names = _offline_names_in(node)
        if not names:
            return
        line = getattr(node, "lineno", 0)
        found.setdefault(
            (line, rule),
            StaticViolation(path=path, line=line, symbol=", ".join(names), rule=rule),
        )

    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            flag(node, RULE_NO_OFFLINE_SORT)
        elif isinstance(node, ast.Call):
            callee = _callee_name(node.func)
            if _is_sort_call(node) or callee in SELECT_SINKS:
                flag(node, RULE_NO_OFFLINE_SORT)
            if callee in DELETE_SINKS:
                flag(node, RULE_NO_LOSS_AUTO_DELETE)

    return sorted(found.values(), key=lambda item: (item.line, item.rule))


def scan_tree(root: Path) -> list[StaticViolation]:
    """Scan every module under a tree for offline-metric-driven ordering or deletion.

    The owned selection tree scans clean (CG-4C-06a/c); a module that ranks or
    auto-deletes by an offline metric is a finding.

    Args:
        root: Directory to scan recursively.

    Returns:
        (list[StaticViolation]) Findings sorted by path and line.
    """
    violations: list[StaticViolation] = []
    for path in sorted(root.rglob("*.py")):
        violations.extend(scan_source(path, path.read_text(encoding="utf-8")))
    return sorted(violations, key=lambda item: (str(item.path), item.line, item.rule))
