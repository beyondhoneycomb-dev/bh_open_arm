"""Acceptance ④ — zero physical-force-unit labels ("N") in the grasp-force UI.

Grasp force is per-unit only: the per-unit-to-force constant is undetermined (spec 12
§5-Q14) and no load cell is used, so displaying grasp force in a physical unit is the
FAIL_BLOCKING case. The check has two layers:

* A package-wide AST scan asserts no string literal — docstrings included — carries an
  unambiguous force/torque unit spelling. Explanations of why no such unit is used live
  in `#` comments, which are not string literals and so are not user-facing.
* A surface scan asserts the grasp labels and the formatted grasp-force line a user
  actually sees carry no isolated Newton unit token ("N") either.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import backend.temp_gripper as temp_gripper_pkg
from backend.temp_gripper.grasp import GraspForceMonitor
from backend.temp_gripper.labels import USER_FACING_GRASP_LABELS

_PACKAGE_DIR = Path(temp_gripper_pkg.__file__).resolve().parent

# Unambiguous force/torque unit spellings that never occur in ordinary prose, so a
# scan of every string literal (docstrings included) is safe from false positives.
_FORBIDDEN_UNIT_TOKENS = ("Nm", "N-m", "N·m", "N⋅m", "newton", "Newton")

# The isolated Newton force-unit symbol as it would appear on a user-facing label
# ("5 N", "force (N)"). Case-sensitive: the unit is a capital N; lowercase n is not it.
_NEWTON_UNIT = re.compile(r"\bN\b")


def _string_literals(path: Path) -> list[str]:
    """Return every string-constant literal in a module's AST."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def test_no_unit_token_in_any_package_string_literal() -> None:
    """No module in the package carries a force/torque unit in any string literal."""
    offenders: list[tuple[str, str, str]] = []
    modules = sorted(_PACKAGE_DIR.glob("*.py"))
    assert modules, "the package has no modules to scan; the check would be vacuous"
    for module in modules:
        for literal in _string_literals(module):
            for token in _FORBIDDEN_UNIT_TOKENS:
                if token in literal:
                    offenders.append((module.name, token, literal[:60]))
    assert not offenders, f"a force/torque unit reached a string literal: {offenders}"


def test_grasp_labels_carry_no_force_unit() -> None:
    """The exposed grasp labels are non-empty and carry no Newton or torque unit."""
    assert USER_FACING_GRASP_LABELS
    for label in USER_FACING_GRASP_LABELS:
        assert not _NEWTON_UNIT.search(label), f"{label!r} carries a Newton unit"
        for token in _FORBIDDEN_UNIT_TOKENS:
            assert token not in label, f"{label!r} carries {token!r}"


def test_formatted_grasp_line_carries_no_force_unit() -> None:
    """The grasp-force line a user actually sees is per-unit with no force unit."""
    monitor = GraspForceMonitor()
    lines = [monitor.format_status(value) for value in (0.0, 0.04, 0.4, 0.9, -0.9, 1.5)]
    for line in lines:
        assert not _NEWTON_UNIT.search(line), f"{line!r} carries a Newton unit"
        for token in _FORBIDDEN_UNIT_TOKENS:
            assert token not in line, f"{line!r} carries {token!r}"
    # The line must state its per-unit nature rather than implying a physical unit.
    assert "per-unit" in monitor.format_status(0.4)
