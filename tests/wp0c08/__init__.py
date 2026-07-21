"""WP-0C-08 acceptance suite — the three-axis policy compatibility matrix.

Shared repository paths, resolved from this file so the suite is independent of the
working directory.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_MATRIX_DIR = REPO_ROOT / "backend" / "policy_matrix"
POLICY_COMPAT_YAML = REPO_ROOT / "contracts" / "policy_compat.yaml"


def numeric_literals(path: Path) -> set[float]:
    """Return the numeric literals a source file uses in code.

    Parses the file and collects every `int`/`float` constant node, so a number
    appearing only in a docstring, comment, or identifier (`max_state_dim_default_32`)
    is not counted — only a value written into logic is. This is what lets the
    "no hardcoded ceiling / no stale literal" checks target real literals rather
    than prose that happens to mention the number.

    Args:
        path: Python source file to scan.

    Returns:
        (set[float]) Distinct numeric literal values used in code.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[float] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, (int, float))
            and not isinstance(node.value, bool)
        ):
            found.add(float(node.value))
    return found


__all__ = [
    "POLICY_COMPAT_YAML",
    "POLICY_MATRIX_DIR",
    "REPO_ROOT",
    "numeric_literals",
]
