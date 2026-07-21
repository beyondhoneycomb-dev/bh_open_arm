"""F23 static check — no `connect()` on a mode-transition path (`14` F23, acceptance ⑦).

The runtime guard (`connect_guard`) catches a re-connect only on the paths a run exercises.
The static half reads every line: it flags any `connect()` call located inside a function
that is a mode-transition handler, whether the handler is marked with `@mode_transition` or
merely named like one. This is the "detect it in mode-transition paths" half of F23, checked
over the whole source rather than the paths that happened to run.
"""

from __future__ import annotations

import ast
from pathlib import Path

from ops.telemetry.connect_guard import mode_transition
from ops.telemetry.staticcheck import StaticViolation, iter_python

# The marker decorator's source name — an explicitly annotated transition handler.
_MARKER_DECORATOR = mode_transition.__name__

# Name fragments that, on their own, denote a mode-transition handler. Kept to unambiguous
# spellings so an unrelated function does not read as a transition path by accident.
_TRANSITION_NAME_FRAGMENTS = (
    "mode_transition",
    "switch_mode",
    "change_mode",
    "enter_mode",
    "set_mode",
    "transition_to",
)


def _is_transition_name(name: str) -> bool:
    """Report whether a function name denotes a mode-transition handler.

    Args:
        name: The function's name.

    Returns:
        (bool) True when the name contains a transition fragment.
    """
    lowered = name.lower()
    return any(fragment in lowered for fragment in _TRANSITION_NAME_FRAGMENTS)


def _has_marker_decorator(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Report whether a function is decorated with the mode-transition marker.

    Args:
        node: The function definition.

    Returns:
        (bool) True when `@mode_transition` decorates it.
    """
    for decorator in node.decorator_list:
        if isinstance(decorator, ast.Name) and decorator.id == _MARKER_DECORATOR:
            return True
        if isinstance(decorator, ast.Attribute) and decorator.attr == _MARKER_DECORATOR:
            return True
    return False


def _connect_calls(node: ast.AST) -> list[tuple[int, str]]:
    """Collect `connect()` call sites within a subtree.

    Args:
        node: The subtree to walk (a function body).

    Returns:
        (list[tuple[int, str]]) `(line, symbol)` for each connect call.
    """
    calls: list[tuple[int, str]] = []
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        if isinstance(func, ast.Name) and func.id == "connect":
            calls.append((child.lineno, "connect"))
        elif isinstance(func, ast.Attribute) and func.attr == "connect":
            calls.append((child.lineno, f"{_attr_source(func)}"))
    return calls


def _attr_source(attr: ast.Attribute) -> str:
    """Render an attribute call target like `robot.connect` for the report line.

    Args:
        attr: The attribute node whose `.attr` is `connect`.

    Returns:
        (str) A readable `receiver.connect` string, best-effort.
    """
    if isinstance(attr.value, ast.Name):
        return f"{attr.value.id}.{attr.attr}"
    return f"...{attr.attr}"


def find_connect_in_mode_transition(root: Path) -> list[StaticViolation]:
    """Find `connect()` calls on mode-transition paths under a tree.

    A function is a mode-transition handler when it is decorated with `@mode_transition` or
    named like one. Every `connect()` call lexically inside such a function is a finding.

    Args:
        root: Directory (or file) to scan.

    Returns:
        (list[StaticViolation]) One finding per connect call on a transition path, sorted.
    """
    violations: list[StaticViolation] = []
    for path in iter_python(root):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if not (_has_marker_decorator(node) or _is_transition_name(node.name)):
                continue
            violations.extend(
                StaticViolation(
                    path=path,
                    line=line,
                    symbol=symbol,
                    rule=f"connect() on mode-transition path {node.name!r} destroys zeroing (F23)",
                )
                for line, symbol in _connect_calls(node)
            )
    return sorted(violations, key=lambda item: (str(item.path), item.line))
