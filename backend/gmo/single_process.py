"""The load-bearing static proof that the residual is computed in the CAN-bus-owning process.

WP-2C-01's contract and its negative branch: the residual is a function call inside the process
that already owns the CAN bus, and a separate-process placement is FAIL_BLOCKING. A second process
with its own CAN socket is a second silent bind on the bus (FR-SAF-001) — the observer would fight
the actuation loop for the same hardware. The only honest way to check an *absence* (no process is
spawned, no bus is opened) is statically: a runtime test shows only the paths it happened to hit.

So this scans the GMO source tree over the AST for two families of symbol, neither of which the
observer may name, because it receives `(q, q_dot, tau_meas)` as arguments and returns `r`:

  * process-spawning — `multiprocessing` / `subprocess` / a process-pool / `os.fork`: reaching to
    run the residual in its own process.
  * bus/socket-opening and cross-process transport — a raw or CAN socket, python-can's bus, or a
    message-queue transport: reaching to take its own handle on the bus or to talk to a residual
    computed elsewhere.

An AST scan means a symbol in a comment or string cannot trip it. `check_source` runs on one
string (the tests use it to prove the scan bites) and `scan_tree` runs it over the real package,
which the acceptance test asserts is clean. This module names the forbidden symbols as data, so it
excludes itself the way WP-1-06's deprecated-pipeline scan excludes its own constants.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from backend.gmo.errors import SeparateProcessBindingError

RULE_SEPARATE_PROCESS = "gmo-separate-process"
RULE_SECOND_BIND = "gmo-second-bind"

# Modules whose import means the observer is reaching to run in its own process.
_PROCESS_MODULES: frozenset[str] = frozenset(
    {"multiprocessing", "subprocess", "concurrent.futures"}
)
# Call symbols that spawn a process or a process pool.
_PROCESS_SYMBOLS: frozenset[str] = frozenset(
    {"Process", "Popen", "fork", "forkserver", "ProcessPoolExecutor"}
)
# Modules whose import means the observer is reaching to open its own bus/socket or an
# out-of-process transport to a residual computed elsewhere.
_BIND_MODULES: frozenset[str] = frozenset({"socket", "can", "zmq", "nanomsg"})
# Symbols that open a socket/bus or bind one.
_BIND_SYMBOLS: frozenset[str] = frozenset(
    {"socket", "bind", "AF_CAN", "SOCK_RAW", "SocketcanBus", "Bus"}
)


@dataclass(frozen=True)
class Finding:
    """A forbidden reference the scan found.

    Attributes:
        rule: Which absence was violated (`RULE_SEPARATE_PROCESS` or `RULE_SECOND_BIND`).
        module: Path label of the checked source.
        line: 1-indexed source line of the reference.
        symbol: The offending symbol or module.
    """

    rule: str
    module: str
    line: int
    symbol: str

    def __str__(self) -> str:
        return f"{self.module}:{self.line}: {self.rule}: {self.symbol}"


def _module_rule(name: str) -> str | None:
    """Return the rule a forbidden imported module trips, or None when it is allowed."""
    root = name.split(".")[0]
    if name in _PROCESS_MODULES or root in _PROCESS_MODULES:
        return RULE_SEPARATE_PROCESS
    if name in _BIND_MODULES or root in _BIND_MODULES:
        return RULE_SECOND_BIND
    return None


def _import_hits(node: ast.Import | ast.ImportFrom, module: str, line: int) -> list[Finding]:
    """Return findings for an import of a process-spawning or bus/socket module."""
    if isinstance(node, ast.Import):
        names = [alias.name for alias in node.names]
    elif node.module is not None:
        names = [node.module]
    else:
        names = []
    findings: list[Finding] = []
    for name in names:
        rule = _module_rule(name)
        if rule is not None:
            findings.append(Finding(rule, module, line, name))
    return findings


def _symbol_rule(name: str) -> str | None:
    """Return the rule a forbidden symbol trips, or None when it is allowed."""
    if name in _PROCESS_SYMBOLS:
        return RULE_SEPARATE_PROCESS
    if name in _BIND_SYMBOLS:
        return RULE_SECOND_BIND
    return None


def check_source(source: str, module: str) -> list[Finding]:
    """Scan one source string for process-spawn (⟂) and second-bind references.

    Args:
        source: Python source text.
        module: Path label for the findings.

    Returns:
        (list[Finding]) Every forbidden reference, in source order.
    """
    tree = ast.parse(source)
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            findings.extend(_import_hits(node, module, node.lineno))
        elif isinstance(node, ast.Attribute):
            rule = _symbol_rule(node.attr)
            if rule is not None:
                findings.append(Finding(rule, module, node.lineno, node.attr))
        elif isinstance(node, ast.Name):
            rule = _symbol_rule(node.id)
            if rule is not None:
                findings.append(Finding(rule, module, node.lineno, node.id))
    return findings


def scan_tree(root: Path, exclude: tuple[Path, ...] = ()) -> tuple[Finding, ...]:
    """Run both source bans over every `.py` file under `root`.

    This module is excluded by default: it names every forbidden symbol as data, so counting its
    own matches would report a violation that is only the checker describing what it checks.

    Args:
        root: Directory to scan recursively.
        exclude: Extra directories or files to skip (a fixture corpus passes its own).

    Returns:
        (tuple[Finding, ...]) Every finding, in file then source order.
    """
    excluded = tuple(path.resolve() for path in (*exclude, Path(__file__)))
    findings: list[Finding] = []
    for path in sorted(root.rglob("*.py")):
        resolved = path.resolve()
        if resolved in excluded or any(directory in resolved.parents for directory in excluded):
            continue
        relative_parents = path.relative_to(root).parts[:-1]
        if any(part.startswith(".") or part == "__pycache__" for part in relative_parents):
            continue
        findings.extend(check_source(path.read_text(encoding="utf-8"), str(path)))
    return tuple(findings)


def assert_single_process_binding(root: Path, exclude: tuple[Path, ...] = ()) -> None:
    """Refuse a GMO tree that would compute the residual outside the bus-owning process.

    Args:
        root: The GMO package directory to scan.
        exclude: Extra directories or files to skip.

    Raises:
        SeparateProcessBindingError: If any process-spawn or second-bind reference is found.
    """
    findings = scan_tree(root, exclude)
    if findings:
        detail = "; ".join(str(finding) for finding in findings)
        raise SeparateProcessBindingError(
            "GMO residual must be computed in the CAN-bus-owning process; found a separate-process "
            f"or second-bind reference (WP-2C-01 FAIL_BLOCKING): {detail}"
        )
