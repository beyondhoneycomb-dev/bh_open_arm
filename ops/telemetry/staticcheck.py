"""Shared scaffolding for the package's compile-stage (AST) checks.

Two invariants in this package are statements of *absence* — "no rosbag2 dependency anywhere"
(FR-OPS-006) and "no `connect()` on a mode-transition path" (F23). An absence can only be
proven honestly by reading every line, because a runtime test proves only the paths it ran.
So both are AST scans, and both share this violation record and this file-walker.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StaticViolation:
    """A forbidden construct located by an AST scan.

    Attributes:
        path: File the construct was found in.
        line: 1-indexed line.
        symbol: The offending symbol or import name.
        rule: Which invariant was violated, for the report line.
    """

    path: Path
    line: int
    symbol: str
    rule: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.rule}: {self.symbol}"


def iter_python(root: Path) -> list[Path]:
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
