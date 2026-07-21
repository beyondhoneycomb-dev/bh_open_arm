"""Static (compile-stage) enforcement of two lock invariants no runtime test can prove.

An invariant stated as an absence — "no socket opens without the lock", "no second
lock path exists" — can only be checked honestly by reading every line, because a
runtime test proves only the paths it happened to run. So these are AST scans, and
each ships with a violation fixture proving the scan actually bites.

- Acceptance ④ (static half) — **a module that opens a CAN interface must have the
  lock precondition in scope.** `find_can_open_without_lock_import` flags any module
  that constructs an `AF_CAN` socket or a `can[.interface].Bus` yet does not import
  `backend.can.lock`. The lock tree itself opens no CAN socket, so scanning it yields
  nothing — which is the point: the lock layer is a pure precondition, never a socket.
- Acceptance ⑤ — **the lock path is single-valued.** `find_divergent_lock_paths`
  flags any `openarm-…lock` path literal or a bare `/var/lock` / `/run/lock` string
  found *outside* `paths.py`. Every path must be built from `normalize_lock_path`, so
  the `01`/`02` directory disagreement cannot reappear as a second copy in code.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

LOCK_LAYER_MODULE = "backend.can.lock"

# Files that may legitimately name the lock-path literals: `paths.py` is the single
# authority that defines them, and this detector must hold them as its needle table.
# Everywhere else a literal means a second path definition has grown.
DIVERGENT_EXEMPT_FILENAMES = frozenset({"paths.py", "staticcheck.py"})

# Literals that, seen as a path-construction fragment, mean a second lock-path
# definition has grown.
_DIVERGENT_LITERALS = ("openarm-", "/var/lock", "/run/lock")


@dataclass(frozen=True)
class StaticViolation:
    """A forbidden construct found by a scan.

    Attributes:
        path: File the construct was found in.
        line: 1-indexed line.
        symbol: The offending symbol or literal.
        rule: Which invariant was violated, for the report line.
    """

    path: Path
    line: int
    symbol: str
    rule: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.rule}: {self.symbol}"


class _CanOpenVisitor(ast.NodeVisitor):
    """Detect CAN-interface opens and whether the lock layer is imported."""

    def __init__(self) -> None:
        self.imports_lock_layer = False
        self.can_open_lines: list[tuple[int, str]] = []

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802  (ast visitor naming)
        for alias in node.names:
            if alias.name == LOCK_LAYER_MODULE or alias.name.startswith(LOCK_LAYER_MODULE + "."):
                self.imports_lock_layer = True
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        module = node.module or ""
        if module == LOCK_LAYER_MODULE or module.startswith(LOCK_LAYER_MODULE + "."):
            self.imports_lock_layer = True
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802
        if node.attr == "AF_CAN":
            self.can_open_lines.append((node.lineno, "AF_CAN"))
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:  # noqa: N802
        if node.id == "AF_CAN":
            self.can_open_lines.append((node.lineno, "AF_CAN"))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "Bus":
            self.can_open_lines.append((node.lineno, "can.Bus"))
        self.generic_visit(node)


def _iter_python(root: Path) -> list[Path]:
    """Return the Python files under a root, skipping hidden directories.

    Args:
        root: Directory to walk, or a single `.py` file.

    Returns:
        (list[Path]) Sorted Python source files.
    """
    if root.is_file():
        return [root]
    return sorted(
        path
        for path in root.rglob("*.py")
        if not any(part.startswith(".") for part in path.relative_to(root).parts[:-1])
    )


def find_can_open_without_lock_import(root: Path) -> list[StaticViolation]:
    """Find modules that open a CAN interface without importing the lock layer.

    A module that references `AF_CAN` or constructs a `*.Bus` but does not import
    `backend.can.lock` has a socket-open path with no lock precondition in scope —
    the static counterpart of the runtime ordering rejection (acceptance ④).

    Args:
        root: Directory (or file) to scan.

    Returns:
        (list[StaticViolation]) One finding per CAN-open site in an unguarded
        module, sorted by path and line.
    """
    violations: list[StaticViolation] = []
    for path in _iter_python(root):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        visitor = _CanOpenVisitor()
        visitor.visit(tree)
        if visitor.imports_lock_layer:
            continue
        violations.extend(
            StaticViolation(
                path=path,
                line=line,
                symbol=symbol,
                rule="CAN interface opened without the lock layer in scope",
            )
            for line, symbol in visitor.can_open_lines
        )
    return sorted(violations, key=lambda item: (str(item.path), item.line))


def _docstring_constant_ids(tree: ast.AST) -> frozenset[int]:
    """Return the node ids of string constants that are docstrings or bare statements.

    A string that mentions a lock path in prose (a module/class/function docstring)
    is documentation, not a second path construction, so it must not be read as a
    divergent definition. Such strings are exactly the `Constant` values of `Expr`
    statements.

    Args:
        tree: Parsed module.

    Returns:
        (frozenset[int]) Ids of `Constant` string nodes at statement position.
    """
    ids: set[int] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            ids.add(id(node.value))
    return frozenset(ids)


def find_divergent_lock_paths(root: Path) -> list[StaticViolation]:
    """Find lock-path construction literals outside the single path authority.

    Every lock path must be built from `normalize_lock_path`; any `openarm-…lock`
    fragment or bare lock-directory literal used in code elsewhere is a second,
    divergent definition — the `01`/`02` disagreement surviving as two copies
    (acceptance ⑤). Docstrings (prose) and the exempt files (`paths.py`, the
    authority; `staticcheck.py`, this detector's needle table) are not findings.

    Args:
        root: Directory (or file) to scan.

    Returns:
        (list[StaticViolation]) One finding per divergent literal, sorted.
    """
    violations: list[StaticViolation] = []
    for path in _iter_python(root):
        if path.name in DIVERGENT_EXEMPT_FILENAMES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        docstrings = _docstring_constant_ids(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if id(node) in docstrings:
                continue
            violations.extend(
                StaticViolation(
                    path=path,
                    line=node.lineno,
                    symbol=literal,
                    rule="lock-path literal outside the single path authority",
                )
                for literal in _DIVERGENT_LITERALS
                if literal in node.value
            )
    return sorted(violations, key=lambda item: (str(item.path), item.line))
