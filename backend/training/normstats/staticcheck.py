"""Static proof that a split-local statistic never becomes a normalization contract.

`CG-4A-04c` requires proving by STATIC check that zero code paths normalize with
split-local (diagnostic) statistics — validation leakage must be impossible, not
merely discouraged. `build_normalization_contract` is this band's normalization sink:
the point a fitted statistic becomes the model-input contract a checkpoint is pinned
to. A diagnostic (val/test) statistic reaching it is the leakage `FR-TRN-024`/
`FR-DAT-031` forbid.

The type split already makes `build_normalization_contract` reject a `DiagnosticStats`
(it accepts only `NormalizationStats`), but a type can be bypassed through `Any`; this
AST scan closes that. It REUSES the committed definition of "what is a diagnostic
value" (`backend.dataset.stats.staticcheck.DIAGNOSTIC_PRODUCERS`/`DIAGNOSTIC_ATTRS`)
so there is one definition of a diagnostic across the two bands, and only names this
band's own sink. The owned tree scans clean and its one real sink call (`pipeline`,
handed the train normalization) passes, so the scan is not vacuous; a fixture feeding
a diagnostic into the sink is caught, which proves it bites.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable
from pathlib import Path

from backend.actuation import StaticViolation
from backend.dataset.stats.staticcheck import DIAGNOSTIC_ATTRS, DIAGNOSTIC_PRODUCERS

# The normalization-contract sink a diagnostic value must never reach.
CONTRACT_SINKS: frozenset[str] = frozenset({"build_normalization_contract"})

RULE = "a diagnostic (split-local) statistic reaches a normalization contract"


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
    """Scan one module's source for a diagnostic value passed to the contract sink.

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
        if not (isinstance(node, ast.Call) and _callee_name(node.func) in CONTRACT_SINKS):
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
    """Scan every module under a tree for a diagnostic-to-contract flow.

    The owned tree passes (a correct tree returns an empty list, `CG-4A-04c`). A module
    that feeds a diagnostic statistic into `build_normalization_contract` is a finding.

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
