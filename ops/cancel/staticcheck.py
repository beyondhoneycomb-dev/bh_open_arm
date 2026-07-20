"""Static detection of latch call sites outside the package that owns the latch path.

`05` §5.2.1 bans per-workflow local latch implementations, with the reason that a local path is
worthless the moment one workflow forgets to latch. `02a` §-2.3 WP-BOOT-04 acceptance ⑤ turns
that into a checkable predicate: zero hits for any symbol applying the latch outside
`ops/cancel/**`.

Scope is CALL sites, not definitions. A test double implementing `ActuationScheduler` defines a
`latch_to_hold` method legitimately — the contract it implements is owned here, and it is
unreachable except through this package. What the ban is actually about is a workflow *applying*
a latch on its own authority, and that is always a call.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

LATCH_SYMBOLS: frozenset[str] = frozenset({"latch_to_hold"})
OWNER_PACKAGE = Path("ops") / "cancel"


@dataclass(frozen=True)
class LatchViolation:
    """A latch call found outside the owning package."""

    path: Path
    line: int
    symbol: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: latch applied outside {OWNER_PACKAGE}: {self.symbol}"


class _LatchCallVisitor(ast.NodeVisitor):
    """Collect latch call sites in one module."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.violations: list[LatchViolation] = []

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802  (ast visitor naming)
        symbol = self._called_symbol(node)
        if symbol is not None:
            self.violations.append(LatchViolation(path=self.path, line=node.lineno, symbol=symbol))
        self.generic_visit(node)

    @staticmethod
    def _called_symbol(node: ast.Call) -> str | None:
        """Identify a latch symbol being invoked by this call.

        Both direct invocation and `getattr` lookup are treated as calls, because the second is
        the obvious way to route around a check that only understands the first.

        Args:
            node: Call node under inspection.

        Returns:
            (str | None): The latch symbol invoked, or None.
        """
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in LATCH_SYMBOLS:
            return func.attr
        if isinstance(func, ast.Name) and func.id in LATCH_SYMBOLS:
            return func.id
        if isinstance(func, ast.Name) and func.id == "getattr":
            for argument in node.args:
                if isinstance(argument, ast.Constant) and argument.value in LATCH_SYMBOLS:
                    return str(argument.value)
        return None


def _is_owned(path: Path) -> bool:
    """Report whether a file belongs to the package that owns the latch path.

    Ownership is a property of where the file sits, not of where a scan happened to start, so
    the check is made against the absolute path. Deciding it relative to the scan root would
    make `ops/cancel/executor.py` count as owned when scanning the repository and unowned when
    scanning `ops/`.

    Args:
        path: File being scanned.

    Returns:
        (bool): True when the file sits under `ops/cancel/`.
    """
    parts = path.resolve().parts
    owner = OWNER_PACKAGE.parts
    return any(
        parts[index : index + len(owner)] == owner for index in range(len(parts) - len(owner) + 1)
    )


def find_external_latch_calls(
    root: Path,
    exclude: Iterable[Path] = (),
) -> list[LatchViolation]:
    """Scan a tree for latch calls made outside the owning package.

    Args:
        root: Directory to scan recursively.
        exclude: Directories to skip. Violation-fixture corpora are passed here explicitly by
            the caller rather than being skipped by a name convention inside this function, so
            the exemption is visible at the call site instead of hidden in the checker.

    Returns:
        (list[LatchViolation]): Every offending call site, sorted by path and line.
    """
    excluded = tuple(directory.resolve() for directory in exclude)
    violations: list[LatchViolation] = []

    for path in sorted(root.rglob("*.py")):
        resolved = path.resolve()
        if any(directory in resolved.parents for directory in excluded):
            continue
        if _is_owned(path):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        visitor = _LatchCallVisitor(path)
        visitor.visit(tree)
        violations.extend(visitor.violations)

    return sorted(violations, key=lambda item: (str(item.path), item.line))
