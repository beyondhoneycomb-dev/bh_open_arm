"""AST helpers for the WP-1-02 static-symbol acceptances (②③④).

These acceptances are about what the CODE does, not what its prose mentions: the
follower's docstrings legitimately discuss `enable_torque`, `set_zero_position`, and
`0xAA` while the code calls none of the first, exactly one of the second, and never the
third. A text grep cannot tell a call from a comment, so every count here is over the
AST — `Call`, `Attribute`, `Name`, and `Constant` nodes — never the source text.
"""

from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

# The product trees WP-1-02 code lives in or could reach. Tests, fixtures, and the
# vendored library are excluded — the ban is on product code emitting a command, and a
# scanner that fired on a fixture's stand-in method would be unusable.
_PRODUCT_TREES = ("packages", "backend", "contracts")

# The WP-1-02 files themselves, for the checks that are about this WP's own code.
WP102_FILES = (
    _REPO_ROOT / "packages" / "lerobot_robot_openarm" / "openarm_follower_oa.py",
    _REPO_ROOT / "backend" / "calibration" / "schema.py",
    _REPO_ROOT / "backend" / "calibration" / "atomic_io.py",
    _REPO_ROOT / "backend" / "calibration" / "verify.py",
)

# The 0xAA Damiao flash-store command byte, and the name a caller would reference it by.
SAVE_PARAM_BYTE = 0xAA
SAVE_PARAM_NAMES = ("CAN_CMD_SAVE_PARAM", "save_param", "save_parameters", "store_param")


def product_files() -> list[Path]:
    """Return every product Python file (packages/backend/contracts, no pycache)."""
    files: list[Path] = []
    for tree in _PRODUCT_TREES:
        for path in (_REPO_ROOT / tree).rglob("*.py"):
            if "__pycache__" not in path.parts:
                files.append(path)
    return sorted(files)


def _trees(files: tuple[Path, ...] | list[Path]) -> list[ast.AST]:
    """Parse each file into an AST."""
    return [ast.parse(path.read_text(encoding="utf-8"), filename=str(path)) for path in files]


def count_calls(files: tuple[Path, ...] | list[Path], method_name: str) -> int:
    """Count call sites whose callee is `method_name` (as `x.method_name(...)` or bare).

    Args:
        files: Files to scan.
        method_name: The callee name to count.

    Returns:
        (int) Number of matching `Call` nodes.
    """
    total = 0
    for tree in _trees(files):
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr == method_name
                or isinstance(func, ast.Name)
                and func.id == method_name
            ):
                total += 1
    return total


def references_symbol(files: tuple[Path, ...] | list[Path], symbol: str) -> bool:
    """Report whether any file references `symbol` as a Name or Attribute (not prose)."""
    for tree in _trees(files):
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == symbol:
                return True
            if isinstance(node, ast.Attribute) and node.attr == symbol:
                return True
    return False


def uses_int_constant(files: tuple[Path, ...] | list[Path], value: int) -> bool:
    """Report whether any file uses `value` as an integer literal in the AST."""
    for tree in _trees(files):
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and node.value == value
                and isinstance(node.value, int)
            ):
                return True
    return False
