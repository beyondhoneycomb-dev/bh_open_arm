"""Acceptance (3) — zero physical-force-unit ("Nm") labels in the gripper UI strings.

The check is static and exhaustive: it walks the AST of every module in the package
and asserts no string literal — docstrings included — carries a physical torque unit,
because grip force is exposed per-unit only (FR-MAN-016, FR-SAF-024b). Explanations of
*why* no such unit is used live in `#` comments, which are not string literals and so
are not user-facing. The behavioural half asserts the exposed labels and the formatted
force/speed lines a user actually sees are likewise clean.
"""

from __future__ import annotations

import ast
from pathlib import Path

import backend.gripper_endpoint as gripper_pkg
from backend.gripper_endpoint.labels import USER_FACING_LABELS
from backend.gripper_endpoint.posforce import format_force_status, format_speed_status

_PACKAGE_DIR = Path(gripper_pkg.__file__).resolve().parent

# Physical torque-unit spellings a gripper UI string must never carry. The per-unit-to
# force conversion is undetermined, so any of these would assert a calibration we lack.
_FORBIDDEN_TOKENS = ("Nm", "N-m", "N·m")


def _string_literals(path: Path) -> list[str]:
    """Return every string-constant literal in a module's AST."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def test_no_force_unit_token_in_any_package_string_literal() -> None:
    """No module in the package carries a physical torque unit in any string literal."""
    offenders: list[tuple[str, str, str]] = []
    modules = sorted(_PACKAGE_DIR.glob("*.py"))
    assert modules, "the package has no modules to scan; the check would be vacuous"
    for module in modules:
        for literal in _string_literals(module):
            for token in _FORBIDDEN_TOKENS:
                if token in literal:
                    offenders.append((module.name, token, literal[:60]))
    assert not offenders, f"physical force unit reached a UI string: {offenders}"


def test_user_facing_labels_are_present_and_clean() -> None:
    """The exposed label registry is non-empty and carries no forbidden token."""
    assert USER_FACING_LABELS
    for label in USER_FACING_LABELS:
        for token in _FORBIDDEN_TOKENS:
            assert token not in label, f"{label!r} carries {token!r}"


def test_formatted_force_and_speed_lines_are_clean() -> None:
    """The force and speed lines a user actually sees carry no physical torque unit."""
    lines = (format_force_status(0.4), format_speed_status(50.0))
    for line in lines:
        for token in _FORBIDDEN_TOKENS:
            assert token not in line, f"{line!r} carries {token!r}"
    # The force line is per-unit, so it must say so rather than implying a unit.
    assert "per-unit" in format_force_status(0.4)
