"""Static enforcement of the "no `actions_per_chunk` = 50 prefill" absence (CG-4A-07b).

`FR-INF-019` makes `actions_per_chunk` a required argument with no default, and the
negative branch is explicit: the stale official `50` must never be prefilled to hide
a missing value. "Never prefilled" is an absence, and the only honest way to check an
absence is statically — a runtime test only covers the paths it happened to hit. So
this is an AST scan for a literal `50` bound to `actions_per_chunk` in any form
(assignment, dataclass-field default, function-parameter default, call keyword, or
dict entry), and it ships with
a fixture proving the scan actually bites (the WP-BOOT-03 discipline the actuation
`staticcheck` set).

Scope is the adapter tree by default, but the scan takes a root so a UI owner can
point it at the frontend that renders the remote-config form — the prefill it forbids
is exactly a form field defaulted to 50.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

# The required-argument name and the stale value it must never be defaulted to.
ACTIONS_PER_CHUNK_FIELD = "actions_per_chunk"
STALE_PREFILL_VALUE = 50


@dataclass(frozen=True)
class PrefillViolation:
    """A place where `actions_per_chunk` is bound to the stale `50` prefill.

    Attributes:
        path: File the prefill was found in.
        line: 1-indexed line of the binding.
        detail: How the prefill appears (assignment, field default, keyword, dict).
    """

    path: Path
    line: int
    detail: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: actions_per_chunk prefilled with 50 ({self.detail})"


def _is_stale_value(node: ast.expr | None) -> bool:
    """Whether an AST node is the integer literal `50`.

    Args:
        node: The value node, or None.

    Returns:
        (bool) True when the node is the constant 50.
    """
    return isinstance(node, ast.Constant) and node.value == STALE_PREFILL_VALUE


def _target_names(target: ast.expr) -> str | None:
    """Return the simple name a target binds, or None when it is not a plain name.

    Args:
        target: An assignment target node.

    Returns:
        (str | None) The bound name (`Name.id` or `Attribute.attr`), or None.
    """
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    return None


class _PrefillVisitor(ast.NodeVisitor):
    """Collect every binding of `actions_per_chunk` to the stale `50` literal."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.violations: list[PrefillViolation] = []

    def _flag(self, line: int, detail: str) -> None:
        self.violations.append(PrefillViolation(path=self.path, line=line, detail=detail))

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:  # noqa: N802  (ast visitor naming)
        if _target_names(node.target) == ACTIONS_PER_CHUNK_FIELD and _is_stale_value(node.value):
            self._flag(node.lineno, "dataclass/field default")
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
        if _is_stale_value(node.value) and any(
            _target_names(target) == ACTIONS_PER_CHUNK_FIELD for target in node.targets
        ):
            self._flag(node.lineno, "assignment")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        for keyword in node.keywords:
            if keyword.arg == ACTIONS_PER_CHUNK_FIELD and _is_stale_value(keyword.value):
                self._flag(node.lineno, "call keyword")
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._check_arg_defaults(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self._check_arg_defaults(node)
        self.generic_visit(node)

    def _check_arg_defaults(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Flag a parameter named `actions_per_chunk` defaulted to the stale `50`.

        Args:
            node: The function definition whose parameter defaults to inspect.
        """
        positional = [*node.args.posonlyargs, *node.args.args]
        offset = len(positional) - len(node.args.defaults)
        for index, default in enumerate(node.args.defaults):
            arg_name = positional[offset + index].arg
            if arg_name == ACTIONS_PER_CHUNK_FIELD and _is_stale_value(default):
                self._flag(default.lineno, "function default")
        for arg, kw_default in zip(node.args.kwonlyargs, node.args.kw_defaults, strict=True):
            if arg.arg == ACTIONS_PER_CHUNK_FIELD and _is_stale_value(kw_default):
                self._flag(node.lineno, "function default")

    def visit_Dict(self, node: ast.Dict) -> None:  # noqa: N802
        for key, value in zip(node.keys, node.values, strict=True):
            if (
                isinstance(key, ast.Constant)
                and key.value == ACTIONS_PER_CHUNK_FIELD
                and _is_stale_value(value)
            ):
                self._flag(node.lineno, "dict entry")
        self.generic_visit(node)


def scan_source(source: str, path: Path) -> list[PrefillViolation]:
    """Scan one source string for the `actions_per_chunk` = 50 prefill.

    Args:
        source: Python source text.
        path: The path to attribute findings to.

    Returns:
        (list[PrefillViolation]) Findings, in source order.
    """
    visitor = _PrefillVisitor(path)
    visitor.visit(ast.parse(source, filename=str(path)))
    return visitor.violations


def find_actions_per_chunk_prefill(root: Path) -> list[PrefillViolation]:
    """Find every `actions_per_chunk` = 50 prefill under a directory tree (CG-4A-07b).

    Args:
        root: Directory to scan recursively for `.py` sources.

    Returns:
        (list[PrefillViolation]) Findings, sorted by path then line.
    """
    violations: list[PrefillViolation] = []
    for path in sorted(root.rglob("*.py")):
        violations.extend(scan_source(path.read_text(encoding="utf-8"), path))
    return sorted(violations, key=lambda item: (str(item.path), item.line))
