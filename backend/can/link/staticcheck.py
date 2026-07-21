"""Static proof that no code path configures a CAN link — `01` FR-SYS-006 (acceptance ⑤).

FR-SYS-006 is categorical: the backend verifies the link and refuses startup, but it may
not set the link — that is the operator's `lerobot-setup-can` step. An absence like this
can only be checked by reading every line, because a runtime test proves only the paths
it happened to run. So this is an AST scan for process-spawning calls (`subprocess.*`,
`os.system`, `os.popen`, `os.exec*`) whose argument literals form an
`ip link {set,add,del}` mutation.

It targets *calls*, not string literals, on purpose: the setup artifact legitimately
carries the `ip link set … txqueuelen` command as text for the operator to run, and that
data must not read as a violation. Only an actual exec would configure the link. Only the
shell-exec form is in scope; the codebase imports no netlink library (pyroute2), so no
in-process link mutation exists for this scan to miss.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

# Process-spawning callables. A link mutation reaches the kernel only through one of
# these; a bare string holding the same words is inert data.
_SUBPROCESS_FUNCS = frozenset(
    {"run", "Popen", "call", "check_call", "check_output", "getoutput", "getstatusoutput"}
)
_OS_EXEC_FUNCS = frozenset(
    {"system", "popen", "execv", "execve", "execvp", "execvpe", "execl", "execle", "execlp"}
)

# `ip [-flags] link {set|add|del|delete}` as consecutive whitespace-separated tokens —
# the mutating forms. `ip link show` / `ip -details link show` (read-only) never matches.
_LINK_MUTATION = re.compile(r"\bip\b(?:\s+-\S+)*\s+link\s+(?:set|add|del|delete)\b")

_RULE = "process spawn configures a CAN link (ip link set); code must not set the link"


@dataclass(frozen=True)
class StaticViolation:
    """A process-spawning call whose arguments configure a CAN link.

    Attributes:
        path: File the call was found in.
        line: 1-indexed line of the call.
        symbol: The spawn function called, e.g. `subprocess.run`.
        rule: Which invariant was violated, for the report line.
    """

    path: Path
    line: int
    symbol: str
    rule: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.rule}: {self.symbol}"


def _callee_name(node: ast.Call) -> str | None:
    """Return the spawn-function label a call targets, if it is one.

    Recognises `subprocess.<fn>` and `os.<fn>` attribute calls, and a bare `<fn>`
    imported from either module. Returns the `module.fn` label for the report, or None
    when the call is not a process spawn.

    Args:
        node: The call node.

    Returns:
        (str | None) The spawn label, or None.
    """
    func = node.func
    if isinstance(func, ast.Attribute):
        if func.attr in _SUBPROCESS_FUNCS or func.attr in _OS_EXEC_FUNCS:
            base = func.value.id if isinstance(func.value, ast.Name) else "?"
            return f"{base}.{func.attr}"
        return None
    if isinstance(func, ast.Name):
        if func.id in _SUBPROCESS_FUNCS:
            return f"subprocess.{func.id}"
        if func.id in _OS_EXEC_FUNCS:
            return f"os.{func.id}"
    return None


def _arg_text(node: ast.Call) -> str:
    """Join every string constant appearing anywhere in a call's arguments.

    List/tuple command forms (`["ip", "link", "set", …]`) and single-string forms
    (`"ip link set …"`) both collapse to one space-joined string the mutation regex can
    test.

    Args:
        node: The call node.

    Returns:
        (str) The space-joined string constants of the call's arguments.
    """
    parts: list[str] = []
    for arg in [*node.args, *(keyword.value for keyword in node.keywords)]:
        for sub in ast.walk(arg):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                parts.append(sub.value)
    return " ".join(parts)


class _LinkSetVisitor(ast.NodeVisitor):
    """Collect process-spawning calls that mutate a CAN link."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.violations: list[StaticViolation] = []

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802  (ast visitor naming)
        name = _callee_name(node)
        if name is not None and _LINK_MUTATION.search(_arg_text(node)):
            self.violations.append(
                StaticViolation(path=self.path, line=node.lineno, symbol=name, rule=_RULE)
            )
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


def find_link_set_calls(root: Path) -> list[StaticViolation]:
    """Find process spawns that configure a CAN link under a root.

    Args:
        root: Directory (or single `.py` file) to scan.

    Returns:
        (list[StaticViolation]) One finding per link-mutating spawn, sorted by path and
        line. Empty means no code path sets a link — the FR-SYS-006 invariant.
    """
    violations: list[StaticViolation] = []
    for path in _iter_python(root):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        visitor = _LinkSetVisitor(path)
        visitor.visit(tree)
        violations.extend(visitor.violations)
    return sorted(violations, key=lambda item: (str(item.path), item.line))
