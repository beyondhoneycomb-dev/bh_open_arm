"""Static rejection of the one double bind runtime cannot catch: `openarm_driver`.

`01` FR-SYS-010 bans `openarm_driver` from the canonical path because it opens
its own `openarm_can::CANSocket`, giving a second CAN socket on the same
interface as LeRobot's `DamiaoMotorsBus` — a silent double bind (`12` §2.9). A
non-cooperating binder like this is invisible to the cooperative flock, so the
only place to stop it is *before it is imported*. This is that check: any
canonical-path module that pulls in `openarm_driver` — statically, or dynamically
via `importlib.import_module` / `__import__` — is a finding.

The ban is exact, not a prefix sweep: `openarm_control` (IK/FK, no CAN) and
`openarm_ker` (USB, no CAN) are explicitly permitted by FR-SYS-010 and must not
be flagged — over-blocking the sanctioned packages is itself a defect
(acceptance ④). Each scan ships with fixtures proving it bites the banned import
and spares the allowed ones.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

# The package banned from the canonical path (`01` FR-SYS-010): it opens its own
# CAN socket, double-binding the interface LeRobot's DamiaoMotorsBus already holds.
BANNED_DRIVER_MODULE = "openarm_driver"

# The CAN-free packages FR-SYS-010 explicitly permits; naming them must never be a
# finding. Held as data so the over-block guard (acceptance ④) checks the exact set.
ALLOWED_MODULES = frozenset({"openarm_control", "openarm_ker"})

# Call targets whose string argument names a module to import at runtime — the
# dynamic route around a static `import` statement.
_DYNAMIC_IMPORT_FUNCS = frozenset({"import_module", "__import__"})


@dataclass(frozen=True)
class StaticViolation:
    """A forbidden import found by the scan.

    Attributes:
        path: File the import was found in.
        line: 1-indexed line.
        symbol: The offending module name, as written.
        rule: Which invariant was violated, for the report line.
    """

    path: Path
    line: int
    symbol: str
    rule: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.rule}: {self.symbol}"


def _is_banned(module: str) -> bool:
    """Whether a module name is `openarm_driver` or a submodule of it.

    The match is anchored: `openarm_driver` and `openarm_driver.foo` are banned,
    `openarm_control` / `openarm_ker` (and any other `openarm_*`) are not.

    Args:
        module: Dotted module name as written in the import.

    Returns:
        (bool) True when the name resolves into the banned package.
    """
    return module == BANNED_DRIVER_MODULE or module.startswith(BANNED_DRIVER_MODULE + ".")


class _DriverImportVisitor(ast.NodeVisitor):
    """Collect every site that imports `openarm_driver`, static or dynamic."""

    def __init__(self) -> None:
        self.hits: list[tuple[int, str]] = []

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802  (ast visitor naming)
        for alias in node.names:
            if _is_banned(alias.name):
                self.hits.append((node.lineno, alias.name))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        # A relative import (level > 0) has no absolute `openarm_driver` module.
        if node.level == 0 and node.module is not None and _is_banned(node.module):
            self.hits.append((node.lineno, node.module))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        func = node.func
        name = (
            func.attr
            if isinstance(func, ast.Attribute)
            else func.id
            if isinstance(func, ast.Name)
            else None
        )
        if name in _DYNAMIC_IMPORT_FUNCS and node.args:
            first = node.args[0]
            if (
                isinstance(first, ast.Constant)
                and isinstance(first.value, str)
                and _is_banned(first.value)
            ):
                self.hits.append((node.lineno, first.value))
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


def find_banned_driver_import(root: Path) -> list[StaticViolation]:
    """Find every canonical-path import of `openarm_driver`.

    Flags `import openarm_driver[.x]`, `from openarm_driver[.x] import …`, and the
    dynamic forms `importlib.import_module("openarm_driver")` / `__import__(...)`.
    The permitted CAN-free packages (`ALLOWED_MODULES`) are never flagged, so a
    module that imports `openarm_control` or `openarm_ker` alongside a banned
    import yields exactly one finding — the banned one (acceptance ③ and ④).

    Args:
        root: Directory (or file) to scan — the canonical-path tree under CI.

    Returns:
        (list[StaticViolation]) One finding per banned import site, sorted by
        path and line.
    """
    violations: list[StaticViolation] = []
    for path in _iter_python(root):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        visitor = _DriverImportVisitor()
        visitor.visit(tree)
        violations.extend(
            StaticViolation(
                path=path,
                line=line,
                symbol=symbol,
                rule="openarm_driver imported on the canonical path (01 FR-SYS-010)",
            )
            for line, symbol in visitor.hits
        )
    return sorted(violations, key=lambda item: (str(item.path), item.line))
