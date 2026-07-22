"""The negative branch made structural: a Move-to cannot execute without the check.

02b §4.2 WP-2D-09 makes "execute without the check" the ``FAIL_BLOCKING`` failure. A
runtime test can only show the paths it happened to exercise; the guarantee is an
*absence* of any admitted path from an input to motion that skips the checks, and an
absence is proven statically. So this reads ``backend/moveto/gate.py`` with ``ast`` and
pins three facts:

1. Every arm-committing call (``jog.seed`` or ``plan_pose(commit=True)``) lives in one
   method, ``_commit`` — there is no second execution site.
2. ``_commit`` is reached from exactly one place, ``execute``.
3. In ``execute``, the ``report.passed`` guard that returns a refusal stands *before*
   the ``_commit`` call — so deleting the check to force an unconditional execute would
   have to delete the guard, which this test forbids.

The ``plan_pose(commit=False)`` probe in the check path is deliberately not an execution
site: it restores the arm state, so it does not count here.
"""

from __future__ import annotations

import ast

from tests.wp2d09 import GATE_MODULE

_GATE_CLASS = "NumericMoveTo"
_COMMIT_METHOD = "_commit"
_EXECUTE_METHOD = "execute"


def _load_gate_class() -> ast.ClassDef:
    """Parse gate.py and return the NumericMoveTo class node."""
    tree = ast.parse(GATE_MODULE.read_text(encoding="utf-8"), filename=str(GATE_MODULE))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == _GATE_CLASS:
            return node
    raise AssertionError(f"{_GATE_CLASS} not found in {GATE_MODULE}")


def _is_arm_commit_call(node: ast.AST) -> bool:
    """Whether a node is an arm-committing call: jog.seed(...) or plan_pose(commit=True)."""
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr == "seed":
        return True
    if node.func.attr == "plan_pose":
        return any(
            kw.arg == "commit" and isinstance(kw.value, ast.Constant) and kw.value.value is True
            for kw in node.keywords
        )
    return False


def _methods(cls: ast.ClassDef) -> dict[str, ast.FunctionDef]:
    """Return the class's methods by name."""
    return {n.name: n for n in cls.body if isinstance(n, ast.FunctionDef)}


def test_arm_commit_calls_live_only_in_the_commit_method() -> None:
    methods = _methods(_load_gate_class())
    committing = {
        name for name, fn in methods.items() if any(_is_arm_commit_call(n) for n in ast.walk(fn))
    }
    assert committing == {_COMMIT_METHOD}, (
        f"arm-committing calls must live only in {_COMMIT_METHOD}, found in {committing}"
    )


def test_commit_is_reached_only_from_execute() -> None:
    methods = _methods(_load_gate_class())
    callers = {
        name
        for name, fn in methods.items()
        for n in ast.walk(fn)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == _COMMIT_METHOD
    }
    assert callers == {_EXECUTE_METHOD}, f"{_COMMIT_METHOD} must be called only from execute"


def test_execute_guards_the_commit_behind_the_passed_check() -> None:
    execute = _methods(_load_gate_class())[_EXECUTE_METHOD]

    guard_lines = [
        node.lineno
        for node in ast.walk(execute)
        if isinstance(node, ast.If)
        and any(isinstance(a, ast.Attribute) and a.attr == "passed" for a in ast.walk(node.test))
        and any(isinstance(b, ast.Return) for b in ast.walk(node))
    ]
    commit_lines = [
        node.lineno
        for node in ast.walk(execute)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == _COMMIT_METHOD
    ]

    assert guard_lines, "execute must guard on report.passed and return a refusal"
    assert commit_lines, "execute must reach _commit on the passing path"
    # The passed-guard returns before control can reach the commit.
    assert min(guard_lines) < min(commit_lines)
