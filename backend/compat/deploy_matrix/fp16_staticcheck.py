"""Static enforcement that no fp16 inference path is exposed by default (`FR-INF-030`).

`FR-INF-030` states the system does not ship an fp16 inference path by default; it may be
exposed only through a bespoke autocast path that passes an accuracy-regression check.
The exposed precision options are `float32`/`bfloat16` only (`FR-INF-029`, `11` §2.7), and
GR00T's TensorRT switch is `bf16`-only. "Not exposed by default" is an absence, and the
only honest way to check an absence is statically — a runtime test covers only the paths
it happens to hit. So this is an AST scan for a precision-carrying field defaulted to an
fp16 dtype in any form (assignment, dataclass-field default, function-parameter default,
call keyword, or dict entry).

It mirrors the WP-4A-07 `actions_per_chunk`=50 scanner exactly, including shipping the
inline fixture the tests feed `scan_source` to prove the scan actually bites — a scanner
never shown to fire is a scanner not known to work (the WP-BOOT-03 discipline). The scan
takes a root so it can be pointed at both this WP's tree and the committed inference
adapter, proving neither exposes fp16 as a default.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

# The precision-carrying field names an fp16 default would hide behind. `dtype` and
# `precision` are the `11` §2.7 catalog names; `torch_dtype` is the HF/transformers name
# the same choice travels under. A default binding one of these to an fp16 dtype is the
# exact exposure FR-INF-030 forbids.
PRECISION_FIELDS: frozenset[str] = frozenset({"precision", "dtype", "torch_dtype", "policy_dtype"})

# The fp16 dtype spellings, as strings and as dtype attribute/name references. `half` is
# torch's alias for float16. bf16/bfloat16 and float32 are deliberately absent — those
# are the sanctioned options, not the forbidden one.
FP16_STRING_VALUES: frozenset[str] = frozenset({"fp16", "float16", "half"})
FP16_DTYPE_NAMES: frozenset[str] = frozenset({"float16", "half"})


@dataclass(frozen=True)
class Fp16Violation:
    """A place a precision field is defaulted to an fp16 dtype (`FR-INF-030`).

    Attributes:
        path: File the exposure was found in.
        line: 1-indexed line of the binding.
        field: The precision field bound to fp16.
        detail: How the exposure appears (assignment, field default, keyword, dict).
    """

    path: Path
    line: int
    field: str
    detail: str

    def __str__(self) -> str:
        return (
            f"{self.path}:{self.line}: precision field {self.field!r} defaulted to fp16 "
            f"({self.detail})"
        )


def _is_fp16_value(node: ast.expr | None) -> bool:
    """Whether an AST node denotes an fp16 dtype (string, dtype attribute, or name).

    Args:
        node: The value node, or None.

    Returns:
        (bool) True when the node is an fp16 dtype in any recognised spelling.
    """
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str) and node.value in FP16_STRING_VALUES
    if isinstance(node, ast.Attribute):
        return node.attr in FP16_DTYPE_NAMES
    if isinstance(node, ast.Name):
        return node.id in FP16_DTYPE_NAMES
    return False


def _precision_target(target: ast.expr) -> str | None:
    """Return the precision-field name a target binds, or None when it is not one.

    Args:
        target: An assignment target node.

    Returns:
        (str | None) The bound field name when it is a precision field, else None.
    """
    name: str | None = None
    if isinstance(target, ast.Name):
        name = target.id
    elif isinstance(target, ast.Attribute):
        name = target.attr
    return name if name in PRECISION_FIELDS else None


class _Fp16Visitor(ast.NodeVisitor):
    """Collect every default binding of a precision field to an fp16 dtype."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.violations: list[Fp16Violation] = []

    def _flag(self, line: int, field: str, detail: str) -> None:
        self.violations.append(Fp16Violation(path=self.path, line=line, field=field, detail=detail))

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:  # noqa: N802  (ast visitor naming)
        field = _precision_target(node.target)
        if field is not None and _is_fp16_value(node.value):
            self._flag(node.lineno, field, "dataclass/field default")
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
        if _is_fp16_value(node.value):
            for target in node.targets:
                field = _precision_target(target)
                if field is not None:
                    self._flag(node.lineno, field, "assignment")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        for keyword in node.keywords:
            if keyword.arg in PRECISION_FIELDS and _is_fp16_value(keyword.value):
                self._flag(node.lineno, keyword.arg, "call keyword")
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._check_arg_defaults(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self._check_arg_defaults(node)
        self.generic_visit(node)

    def _check_arg_defaults(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Flag a precision parameter defaulted to an fp16 dtype.

        Args:
            node: The function definition whose parameter defaults to inspect.
        """
        positional = [*node.args.posonlyargs, *node.args.args]
        offset = len(positional) - len(node.args.defaults)
        for index, default in enumerate(node.args.defaults):
            arg_name = positional[offset + index].arg
            if arg_name in PRECISION_FIELDS and _is_fp16_value(default):
                self._flag(default.lineno, arg_name, "function default")
        for arg, kw_default in zip(node.args.kwonlyargs, node.args.kw_defaults, strict=True):
            if arg.arg in PRECISION_FIELDS and _is_fp16_value(kw_default):
                self._flag(node.lineno, arg.arg, "function default")

    def visit_Dict(self, node: ast.Dict) -> None:  # noqa: N802
        for key, value in zip(node.keys, node.values, strict=True):
            if (
                isinstance(key, ast.Constant)
                and key.value in PRECISION_FIELDS
                and _is_fp16_value(value)
            ):
                self._flag(node.lineno, str(key.value), "dict entry")
        self.generic_visit(node)


def scan_source(source: str, path: Path) -> list[Fp16Violation]:
    """Scan one source string for a precision field defaulted to fp16 (`FR-INF-030`).

    Args:
        source: Python source text.
        path: The path to attribute findings to.

    Returns:
        (list[Fp16Violation]) Findings, in source order.
    """
    visitor = _Fp16Visitor(path)
    visitor.visit(ast.parse(source, filename=str(path)))
    return visitor.violations


def find_fp16_default_exposure(root: Path) -> list[Fp16Violation]:
    """Find every fp16 default exposure under a directory tree (CG-4B-04d).

    Args:
        root: Directory to scan recursively for `.py` sources.

    Returns:
        (list[Fp16Violation]) Findings, sorted by path then line.
    """
    violations: list[Fp16Violation] = []
    for path in sorted(root.rglob("*.py")):
        violations.extend(scan_source(path.read_text(encoding="utf-8"), path))
    return sorted(violations, key=lambda item: (str(item.path), item.line))
