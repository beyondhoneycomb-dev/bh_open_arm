"""The static check that the feedback path is a call, not a message (`12` FR-SAF-006).

WP-2C-10's acceptance ② is that the feedback path does not go via IPC or a network
transport, and its negative branch is that an IPC-routed implementation is `SUPERSEDED`.
This module makes that mechanically checkable: it parses every source file of a package
and flags any import of a transport that would carry the trip across a process or network
boundary. Applied to `backend.feedback`, it must return clean; applied to a module that
imports `socket`, it must flag it — a check that cannot fail is a fake green, so the tests
exercise both directions.

The check is import-level on purpose. A trip dispatched over a transport must import that
transport somewhere in the path, so a clean import surface is a sufficient proof of
locality for this package, whose whole job is to make three direct calls.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

# Root module names whose presence means the feedback would cross a process or network
# boundary rather than make a direct call. Grouped by how they would carry the trip:
#   - raw sockets and TLS,
#   - an event loop mediating network IO,
#   - HTTP and WebSocket clients,
#   - RPC and message-bus transports,
#   - cross-process primitives (spawned processes, shared memory).
# Matching is on the first dotted component, so `http.client`, `grpc.aio`,
# `urllib.request`, and `multiprocessing.connection` are all caught by their roots.
BANNED_TRANSPORT_MODULES = frozenset(
    {
        "socket",
        "ssl",
        "asyncio",
        "selectors",
        "http",
        "urllib",
        "requests",
        "httpx",
        "aiohttp",
        "websockets",
        "websocket",
        "grpc",
        "xmlrpc",
        "zmq",
        "multiprocessing",
        "subprocess",
        "mmap",
    }
)

_PYTHON_GLOB = "*.py"


@dataclass(frozen=True)
class LocalityViolation:
    """One banned transport import found in a package under check.

    Attributes:
        file: Root-relative POSIX path of the source file.
        line: 1-indexed line of the import statement.
        module: The banned root module name that was imported.
    """

    file: str
    line: int
    module: str

    def as_line(self) -> str:
        """Render the violation as a single diagnostic line.

        Returns:
            (str) `<file>:<line> imports <module>`.
        """
        return f"{self.file}:{self.line} imports {self.module}"


def _imported_roots(node: ast.AST) -> list[tuple[int, str]]:
    """Return the (line, root-module) pairs an import statement introduces.

    Relative imports (`from . import x`) are in-package and never a transport, so they
    contribute nothing.

    Args:
        node: Any AST node walked from the tree; non-import nodes contribute nothing.

    Returns:
        (list) `(line, root)` pairs, empty for non-import or relative-import nodes.
    """
    if isinstance(node, ast.Import):
        return [(node.lineno, alias.name.split(".")[0]) for alias in node.names]
    if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
        return [(node.lineno, node.module.split(".")[0])]
    return []


def scan_imports(
    package_dir: Path | None = None, root: Path | None = None
) -> tuple[LocalityViolation, ...]:
    """Flag every banned transport import in a package's source tree.

    Args:
        package_dir: Directory to scan; defaults to this package (`backend/feedback`), so
            `scan_imports()` self-applies the check to the feedback path.
        root: Repository root the reported paths are made relative to; defaults to the
            two levels above the default package (the repository root).

    Returns:
        (tuple) Violations, sorted by file then line. Empty means the package is local.
    """
    package = package_dir if package_dir is not None else Path(__file__).resolve().parent
    base = root if root is not None else Path(__file__).resolve().parents[2]
    violations: list[LocalityViolation] = []
    for source in sorted(package.rglob(_PYTHON_GLOB)):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        try:
            relative = source.resolve().relative_to(base).as_posix()
        except ValueError:
            relative = source.as_posix()
        for node in ast.walk(tree):
            for line, module in _imported_roots(node):
                if module in BANNED_TRANSPORT_MODULES:
                    violations.append(LocalityViolation(file=relative, line=line, module=module))
    return tuple(sorted(violations, key=lambda item: (item.file, item.line)))


def is_in_process(package_dir: Path | None = None) -> bool:
    """Whether a package's feedback path stays in-process (no banned transport import).

    Args:
        package_dir: Directory to check; defaults to the feedback package.

    Returns:
        (bool) True when no banned transport is imported.
    """
    return not scan_imports(package_dir)
