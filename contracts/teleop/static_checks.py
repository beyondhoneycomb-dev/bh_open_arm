"""Static checks that make two CTR-TEL@v1 rules bite rather than merely assert.

`02b` §5.2 WP-3A-03 turns two properties into build-blocking checks, and the real
teleoperator is a Wave-3B deliverable, so — like `contracts.prim.redefinition` —
the checks are proven here against source rather than a running device:

- **`get_action()` is non-blocking (acceptance ③).** Pose reception runs on a
  separate thread; `get_action()` reads the latest snapshot and must not perform
  blocking IO (`FR-TEL-005`). `scan_blocking_io` finds a blocking call inside the
  method by AST, so a teleoperator that receives inside `get_action()` fails.
- **No shared primitive is redefined.** `CTR-TEL@v1` consumes `CTR-PRIM@v1` by
  import; `scan_teleop_redefinitions` reuses the frozen `CTR-PRIM` scanner over this
  package's own modules, so a teleop file that forks a primitive is caught.

This module is machinery (`EXCLUSIVE`, not `CONTRACT_FROZEN`): the reserved set and
the scanner both live in `CTR-PRIM@v1`, so this file can change without moving the
`CTR-TEL@v1` frozen hash. Pure standard library plus `contracts.prim`; no robot
stack, so it runs in the AI-offline light lane.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from contracts.prim import Redefinition, check_no_redefinition

# The default method the non-blocking rule guards.
NON_BLOCKING_METHOD = "get_action"

# Call names that block the calling thread when run inside `get_action()`: the socket
# receive family, `time.sleep`, a thread `join`, a lock `acquire`, an event `wait`,
# `select` and `input`. A pose receiver belongs on its own thread, so any of these
# inside `get_action()` is the blocking-IO defect `FR-TEL-005` forbids.
BLOCKING_CALL_NAMES = frozenset(
    {
        "sleep",
        "recv",
        "recvfrom",
        "recv_into",
        "recvmsg",
        "recvmsg_into",
        "accept",
        "connect",
        "join",
        "acquire",
        "wait",
        "select",
        "input",
    }
)

# Keyword arguments whose value turns a would-be blocking call non-blocking:
# `block=False` / `blocking=False`, and `timeout=0`. A call carrying one of these is
# not counted, so a deliberate non-blocking `queue.get(block=False)` is allowed.
_NON_BLOCKING_FLAGS = ("block", "blocking")
_TIMEOUT_KEYWORD = "timeout"


@dataclass(frozen=True)
class BlockingCall:
    """One blocking call found inside a scanned method.

    Attributes:
        path: File the call was found in.
        line: 1-indexed line of the call.
        call: The blocking callable's name (the attribute or bare name).
        method: The method the call sits inside.
    """

    path: str
    line: int
    call: str
    method: str


def _call_name(node: ast.Call) -> str | None:
    """Return the called name — an attribute's `attr` or a bare `Name`'s id.

    Args:
        node: A call expression.

    Returns:
        (str | None) The callable's name, or None when it is neither shape.
    """
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    if isinstance(node.func, ast.Name):
        return node.func.id
    return None


def _is_made_non_blocking(node: ast.Call) -> bool:
    """Report whether a call opts out of blocking via a keyword.

    Args:
        node: A call expression.

    Returns:
        (bool) True when `block`/`blocking` is `False` or `timeout` is `0`.
    """
    for keyword in node.keywords:
        if keyword.arg in _NON_BLOCKING_FLAGS and _is_false(keyword.value):
            return True
        if keyword.arg == _TIMEOUT_KEYWORD and _is_zero(keyword.value):
            return True
    return False


def _is_false(node: ast.expr) -> bool:
    """Report whether an expression is the literal `False`."""
    return isinstance(node, ast.Constant) and node.value is False


def _is_zero(node: ast.expr) -> bool:
    """Report whether an expression is the literal `0` (int or float), never bool."""
    if not isinstance(node, ast.Constant) or isinstance(node.value, bool):
        return False
    return node.value in (0, 0.0)


def _methods_named(tree: ast.Module, method: str) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Return every function/method defined with a given name, anywhere in a module.

    Args:
        tree: A parsed module.
        method: The method name to collect.

    Returns:
        (list) Matching function definitions, sync or async.
    """
    found: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == method:
            found.append(node)
    return found


def scan_blocking_io(path: Path, method: str = NON_BLOCKING_METHOD) -> list[BlockingCall]:
    """Find blocking calls inside a named method of a module.

    Args:
        path: Python file to scan (a teleoperator module).
        method: The method whose body must not block (`get_action` by default).

    Returns:
        (list[BlockingCall]) One entry per blocking call inside the method, in source
            order; empty when the method reads a snapshot without blocking.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits: list[BlockingCall] = []
    for function in _methods_named(tree, method):
        for node in ast.walk(function):
            if not isinstance(node, ast.Call):
                continue
            name = _call_name(node)
            if name in BLOCKING_CALL_NAMES and not _is_made_non_blocking(node):
                hits.append(BlockingCall(str(path), node.lineno, str(name), method))
    return hits


def get_action_is_non_blocking(path: Path) -> bool:
    """Report whether a module's `get_action` performs no blocking IO.

    Args:
        path: Python file to scan.

    Returns:
        (bool) True when `get_action` contains no unguarded blocking call.
    """
    return not scan_blocking_io(path, NON_BLOCKING_METHOD)


# The CTR-TEL@v1 contract modules the no-redefinition scan covers. Every one consumes
# `CTR-PRIM@v1` by import and must define none of its reserved primitives.
TELEOP_CONTRACT_FILES = (
    "contracts/teleop/__init__.py",
    "contracts/teleop/schema.py",
    "contracts/teleop/static_checks.py",
    "contracts/teleop/reverify.py",
)


def scan_teleop_redefinitions(repo_root: Path) -> list[Redefinition]:
    """Scan the CTR-TEL@v1 modules for any redefinition of a CTR-PRIM primitive.

    Reuses the frozen `CTR-PRIM@v1` scanner rather than restating the reserved set, so
    the two contracts share one definition of what a redefinition is.

    Args:
        repo_root: Repository root the teleop modules live under.

    Returns:
        (list[Redefinition]) Every primitive redefinition found in this package; empty
            when the contract consumes the primitives purely by import.
    """
    paths = [repo_root / relative for relative in TELEOP_CONTRACT_FILES]
    return check_no_redefinition([path for path in paths if path.is_file()])
