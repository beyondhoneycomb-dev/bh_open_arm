"""Static (compile-stage) proof that the E-Stop is not wired to `record_loop` events.

`FR-SAF-073` is stated as an absence: the safety stop must be the loop changing what it
sends, never the loop stopping. LeRobot's `record_loop()` exposes an `events` dict —
`{"exit_early", "rerecord_episode", "stop_recording"}` — that is *episode* control, and
`stop_recording` merely leaves the loop without holding the motors (`12` §2.7.2). Wiring
that to the E-Stop is exactly the drop-the-arm defect the requirement forbids.

An absence is only honestly checked statically, so this is an AST scan of the reaction
tree for any reference to `record_loop` or `stop_recording` (name, attribute, or the
`events["stop_recording"]` string key). A correct reaction path drives the actuation
scheduler's tick and never touches episode control, so the tree scans clean; the
violation fixture wires `stop_recording` to a latch engage and is caught, proving the
scan bites rather than passing vacuously (the WP-BOOT-03 discipline).
"""

from __future__ import annotations

import ast
from collections.abc import Iterable
from pathlib import Path

from backend.actuation import StaticViolation

# The episode-control symbols the E-Stop path must never reference (`12` §2.7.2). The
# string key is scanned too, because `events["stop_recording"]` reaches the event by a
# constant subscript, not by a name a symbol scan would see.
FORBIDDEN_SYMBOLS: frozenset[str] = frozenset({"record_loop", "stop_recording"})
FORBIDDEN_STRINGS: frozenset[str] = frozenset({"stop_recording"})

RULE = "record_loop stop_recording wired to E-Stop"


class _EStopWiringVisitor(ast.NodeVisitor):
    """Collect references to episode-control symbols and the `stop_recording` string key."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.violations: list[StaticViolation] = []

    def _flag(self, symbol: str, line: int) -> None:
        """Record one violation at a source line.

        Args:
            symbol: The offending symbol or string.
            line: 1-indexed source line.
        """
        self.violations.append(StaticViolation(path=self.path, line=line, symbol=symbol, rule=RULE))

    def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802  (ast visitor naming)
        if node.attr in FORBIDDEN_SYMBOLS:
            self._flag(node.attr, node.lineno)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:  # noqa: N802
        if node.id in FORBIDDEN_SYMBOLS:
            self._flag(node.id, node.lineno)
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:  # noqa: N802
        # Only a constant subscript key (`events["stop_recording"]`) is a wiring; a
        # bare string in a set literal (this module's own token list) is a Constant
        # under a Set, not under a Subscript, so it is not matched — the checker does
        # not flag its own definitions.
        key = node.slice
        if isinstance(key, ast.Constant) and key.value in FORBIDDEN_STRINGS:
            self._flag(key.value, node.lineno)
        self.generic_visit(node)


def find_estop_stop_recording_wiring(
    root: Path,
    exclude: Iterable[Path] = (),
) -> list[StaticViolation]:
    """Find any `record_loop`/`stop_recording` reference in a tree (acceptance ②).

    The reaction tree owns no such reference — the loop that keeps running is the
    actuation scheduler's, not `record_loop` — so a clean tree returns an empty list.
    A fixture that wires the episode event to a stop is a finding.

    Args:
        root: Directory to scan recursively.
        exclude: Directories to skip explicitly (fixture corpora pass their own).

    Returns:
        (list[StaticViolation]) Offending references, sorted by path and line.
    """
    excluded = tuple(directory.resolve() for directory in exclude)
    violations: list[StaticViolation] = []
    for path in sorted(root.rglob("*.py")):
        resolved = path.resolve()
        if any(directory in resolved.parents for directory in excluded):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        visitor = _EStopWiringVisitor(path)
        visitor.visit(tree)
        violations.extend(visitor.violations)
    return sorted(violations, key=lambda item: (str(item.path), item.line))
