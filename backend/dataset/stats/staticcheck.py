"""Static proof that a diagnostic (split-local) statistic never becomes a normalization input.

WP-3D-03 ① requires this as a STATIC check: split-local statistics are diagnostic
only and must not be a normalization input (`02b` §8.2 WP-3D-03 ①). The type split
(`DiagnosticStats` is not a `NormalizationStats`) already makes `build_normalizer`
reject one, but a type can be bypassed through `Any`; this AST scan closes that by
forbidding a diagnostic-producing value from being passed to a normalization sink
anywhere in the owned tree.

The scan collects the names a module binds to a diagnostic producer
(`compute_diagnostic_stats(...)`, `DiagnosticStats(...)`) and flags any call to a
normalization sink (`build_normalizer`) that receives one of those names, a direct
diagnostic-producer call, or a `.diagnostics` access. The owned tree scans clean and
its one real sink call in `pipeline` passes (it is handed the train normalization,
not a diagnostic), so the scan is not vacuous; a fixture that feeds a diagnostic into
the sink is caught, which proves it bites (the WP-BOOT-03 discipline). The tokens
appear here only as data in set literals, so the checker never flags its own
definitions.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable
from pathlib import Path

from backend.actuation import StaticViolation

# Calls whose result is a diagnostic (split-local) statistic.
DIAGNOSTIC_PRODUCERS: frozenset[str] = frozenset({"compute_diagnostic_stats", "DiagnosticStats"})
# Attribute names that read a diagnostic statistic off an aggregate object.
DIAGNOSTIC_ATTRS: frozenset[str] = frozenset({"diagnostics", "diagnostic"})
# The normalization-input sinks a diagnostic value must never reach.
NORMALIZATION_SINKS: frozenset[str] = frozenset({"build_normalizer"})

RULE = "a diagnostic (split-local) statistic reaches a normalization input"


def _callee_name(node: ast.expr) -> str:
    """Return the simple name a call targets (`f(...)` or `mod.f(...)`)."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _is_diagnostic_expr(node: ast.expr, diagnostic_names: set[str]) -> bool:
    """Whether an argument expression carries a diagnostic statistic."""
    if isinstance(node, ast.Call):
        return _callee_name(node.func) in DIAGNOSTIC_PRODUCERS
    if isinstance(node, ast.Name):
        return node.id in diagnostic_names
    if isinstance(node, ast.Attribute):
        return node.attr in DIAGNOSTIC_ATTRS
    if isinstance(node, ast.Subscript):
        return isinstance(node.value, ast.Attribute) and node.value.attr in DIAGNOSTIC_ATTRS
    return False


def _diagnostic_names(tree: ast.AST) -> set[str]:
    """Collect names bound to a diagnostic producer anywhere in the module."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Call)
            and _callee_name(node.value.func) in DIAGNOSTIC_PRODUCERS
        ):
            names.update(target.id for target in node.targets if isinstance(target, ast.Name))
    return names


def scan_source(path: Path, source: str) -> list[StaticViolation]:
    """Scan one module's source for a diagnostic value passed to a normalization sink.

    Args:
        path: The module path, for the violation record.
        source: The module source text.

    Returns:
        (list[StaticViolation]) Offending sink calls, in source order.
    """
    tree = ast.parse(source, filename=str(path))
    diagnostic_names = _diagnostic_names(tree)
    violations: list[StaticViolation] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and _callee_name(node.func) in NORMALIZATION_SINKS):
            continue
        arguments = [*node.args, *(keyword.value for keyword in node.keywords)]
        if any(_is_diagnostic_expr(argument, diagnostic_names) for argument in arguments):
            violations.append(
                StaticViolation(
                    path=path, line=node.lineno, symbol=_callee_name(node.func), rule=RULE
                )
            )
    return violations


def scan_tree(root: Path, exclude: Iterable[Path] = ()) -> list[StaticViolation]:
    """Scan every module under a tree for a diagnostic-to-normalization flow.

    The owned tree passes (a correct tree returns an empty list, WP-3D-03 ①). A
    module that feeds a diagnostic statistic into `build_normalizer` is a finding.

    Args:
        root: Directory to scan recursively.
        exclude: Directories to skip (a fixture corpus passes its own).

    Returns:
        (list[StaticViolation]) Offending sink calls, sorted by path and line.
    """
    excluded = tuple(directory.resolve() for directory in exclude)
    violations: list[StaticViolation] = []
    for path in sorted(root.rglob("*.py")):
        resolved = path.resolve()
        if any(directory in resolved.parents for directory in excluded):
            continue
        violations.extend(scan_source(path, path.read_text(encoding="utf-8")))
    return sorted(violations, key=lambda item: (str(item.path), item.line))
