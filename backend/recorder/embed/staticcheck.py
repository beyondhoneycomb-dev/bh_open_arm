"""Static proof that the recorder embed spawns no process and owns no key listener.

Two of WP-3B-11's acceptance criteria are stated as absences, and an absence is
only honestly checked statically (`02b` §6.2 WP-3B-11):

- ① the record loop is in-process — the embed never spawns the record console
  script as a subprocess, nor invokes it in-process (the CLI reconnects the robot
  every call and destroys its zero calibration). This is enforced by forbidding
  the spawn mechanisms themselves — `subprocess`, `pty`, the `os` spawn/exec
  family — and the record-script module, so there is no way left to launch it.
- ② the `events` dict is backend-owned — the embed depends on no `pynput` global
  hook and no controlling-TTY reader. Enforced by forbidding those modules
  (`pynput`, `termios`, `tty`, LeRobot's `keyboard_input`) and the listener
  factory the recorder would otherwise call.

The scan is an AST walk of every module under the embed tree. The embed itself
scans clean; a violation fixture that imports `subprocess` or `pynput` is caught,
which proves the scan bites rather than passing vacuously (the WP-BOOT-03
discipline). The forbidden tokens appear here only as data in set literals — never
as an import, a call, or an attribute — so the checker does not flag its own
definitions.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable
from pathlib import Path

from backend.actuation import StaticViolation

# Modules whose mere import defeats an absence: the first three are how a process
# is spawned, the record-script module is the CLI path even when invoked in-process,
# and the last three are keyboard/TTY listeners the backend must not depend on.
FORBIDDEN_IMPORT_MODULES: frozenset[str] = frozenset(
    {
        "subprocess",
        "pty",
        "lerobot.scripts.lerobot_record",
        "pynput",
        "termios",
        "tty",
        "lerobot.utils.keyboard_input",
    }
)

# Symbols that reach a forbidden capability without importing its module by name:
# a bound `Popen`, and the key-listener factory/backend a recorder would call.
FORBIDDEN_SYMBOLS: frozenset[str] = frozenset(
    {
        "Popen",
        "init_keyboard_listener",
        "TerminalKeyListener",
    }
)

# The `os` process-launching family. Reached as `os.<attr>` (an attribute) or via
# `from os import <attr>`; `os` itself is not forbidden, only these members.
FORBIDDEN_OS_MEMBERS: frozenset[str] = frozenset(
    {
        "system",
        "popen",
        "execl",
        "execle",
        "execlp",
        "execv",
        "execve",
        "execvp",
        "execvpe",
        "spawnl",
        "spawnle",
        "spawnlp",
        "spawnv",
        "spawnve",
        "spawnvp",
        "posix_spawn",
        "posix_spawnp",
        "forkpty",
    }
)

OS_MODULE = "os"
RULE = "recorder embed spawns a process or owns a key listener"


class _AbsenceVisitor(ast.NodeVisitor):
    """Collect any reference that would break the in-process / backend-owned absence."""

    def __init__(self, path: Path) -> None:
        """Start an empty scan of one module.

        Args:
            path: The module being scanned, for the violation record.
        """
        self.path = path
        self.violations: list[StaticViolation] = []

    def _flag(self, symbol: str, line: int) -> None:
        """Record one violation at a source line.

        Args:
            symbol: The offending module, symbol, or member.
            line: 1-indexed source line.
        """
        self.violations.append(StaticViolation(path=self.path, line=line, symbol=symbol, rule=RULE))

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802  (ast visitor naming)
        for alias in node.names:
            if alias.name in FORBIDDEN_IMPORT_MODULES:
                self._flag(alias.name, node.lineno)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        module = node.module or ""
        if module in FORBIDDEN_IMPORT_MODULES:
            self._flag(module, node.lineno)
        elif module == OS_MODULE:
            for alias in node.names:
                if alias.name in FORBIDDEN_OS_MEMBERS:
                    self._flag(f"{OS_MODULE}.{alias.name}", node.lineno)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:  # noqa: N802
        if node.id in FORBIDDEN_SYMBOLS:
            self._flag(node.id, node.lineno)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802
        if node.attr in FORBIDDEN_SYMBOLS:
            self._flag(node.attr, node.lineno)
        elif (
            isinstance(node.value, ast.Name)
            and node.value.id == OS_MODULE
            and node.attr in FORBIDDEN_OS_MEMBERS
        ):
            self._flag(f"{OS_MODULE}.{node.attr}", node.lineno)
        self.generic_visit(node)


def scan_source(path: Path, source: str) -> list[StaticViolation]:
    """Scan one module's source for a process spawn or a key listener.

    Args:
        path: The module path, for the violation record.
        source: The module source text.

    Returns:
        (list[StaticViolation]) Offending references, in source order.
    """
    visitor = _AbsenceVisitor(path)
    visitor.visit(ast.parse(source, filename=str(path)))
    return visitor.violations


def scan_tree(root: Path, exclude: Iterable[Path] = ()) -> list[StaticViolation]:
    """Scan every module under a tree for a process spawn or a key listener.

    The embed tree owns no such reference, so a correct tree returns an empty list
    (acceptance ①/②). A module that imports `subprocess` or `pynput` is a finding.

    Args:
        root: Directory to scan recursively.
        exclude: Directories to skip (a fixture corpus passes its own).

    Returns:
        (list[StaticViolation]) Offending references, sorted by path and line.
    """
    excluded = tuple(directory.resolve() for directory in exclude)
    violations: list[StaticViolation] = []
    for path in sorted(root.rglob("*.py")):
        resolved = path.resolve()
        if any(directory in resolved.parents for directory in excluded):
            continue
        violations.extend(scan_source(path, path.read_text(encoding="utf-8")))
    return sorted(violations, key=lambda item: (str(item.path), item.line))
