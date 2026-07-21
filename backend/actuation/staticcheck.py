"""Static (compile-stage) enforcement of two absences the tick path depends on.

Two of the acceptance gates are stated as things that must **not** be reachable,
and the only honest way to check an absence is statically — a runtime test can only
show the paths it happened to exercise. So these are AST scans, and each ships with
a violation fixture proving the scan actually bites (the WP-BOOT-03 discipline).

- Acceptance ⑥ — **a producer cannot reach the CAN handle.** The single-writer
  invariant is structural (a producer holds only a mailbox), but "structural" is
  only true while no one imports around it. This scan makes reaching for the CAN
  writer's module or its write method, from anywhere outside the owning tree, a
  finding — so the reach fails at check time, not at torque-on.
- Acceptance ⑦ — **`disable_torque` never appears in the stop path.** The stop path
  is a hold frame, not a torque cut (`04` NFR-MAN-002: cutting torque blocks ~8 ms
  single / ~16 ms bimanual and drops a brakeless arm). This scan finds the symbol
  anywhere under the actuation tree; the design simply never uses it, and the scan
  keeps a later edit from quietly introducing it.

Scope is references — imports, calls, attribute and name uses — because that is how
a forbidden capability actually gets pulled in. Defining a method named
`mit_control_batch` on the CAN writer itself is legitimate and lives in the owning
tree, which the owner-exemption skips.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

# The CAN writer's module and the symbols that touch the bus. A producer naming any
# of these is reaching past the mailbox for the handle it must never hold.
CAN_HANDLE_MODULE = "backend.actuation.can_writer"
CAN_HANDLE_SYMBOLS: frozenset[str] = frozenset(
    {"CanWriter", "FakeCanWriter", "mit_control_batch", "_mit_control_batch"}
)

# The torque-cut symbol banned from the stop path (`04` NFR-MAN-002).
DISABLE_TORQUE_SYMBOL = "disable_torque"

# The tree that legitimately owns the CAN writer; references here are not producer
# reaches and are exempt from the acceptance-⑥ scan.
OWNER_PACKAGE = Path("backend") / "actuation"


@dataclass(frozen=True)
class StaticViolation:
    """A forbidden reference found by a scan.

    Attributes:
        path: File the reference was found in.
        line: 1-indexed line of the reference.
        symbol: The offending symbol or module.
        rule: Which absence was violated, for the report line.
    """

    path: Path
    line: int
    symbol: str
    rule: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.rule}: {self.symbol}"


class _SymbolVisitor(ast.NodeVisitor):
    """Collect references to a symbol set and a forbidden import module."""

    def __init__(self, path: Path, symbols: frozenset[str], module: str | None, rule: str) -> None:
        self.path = path
        self._symbols = symbols
        self._module = module
        self._rule = rule
        self.violations: list[StaticViolation] = []

    def _flag(self, symbol: str, line: int) -> None:
        """Record one violation.

        Args:
            symbol: The offending symbol or module string.
            line: 1-indexed source line.
        """
        self.violations.append(
            StaticViolation(path=self.path, line=line, symbol=symbol, rule=self._rule)
        )

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802  (ast visitor naming)
        if self._module is not None:
            for alias in node.names:
                if alias.name == self._module or alias.name.startswith(self._module + "."):
                    self._flag(alias.name, node.lineno)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        if self._module is not None and node.module is not None:
            if node.module == self._module or node.module.startswith(self._module + "."):
                self._flag(node.module, node.lineno)
            # `from backend.actuation import can_writer` names the module as an alias.
            elif self._module.startswith(node.module + "."):
                tail = self._module[len(node.module) + 1 :]
                for alias in node.names:
                    if alias.name == tail:
                        self._flag(self._module, node.lineno)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802
        if node.attr in self._symbols:
            self._flag(node.attr, node.lineno)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:  # noqa: N802
        if node.id in self._symbols:
            self._flag(node.id, node.lineno)
        self.generic_visit(node)


def _is_owned(path: Path) -> bool:
    """Whether a file sits under the CAN-writer's owning tree.

    Args:
        path: File being scanned.

    Returns:
        (bool) True when the file is under `backend/actuation/`.
    """
    parts = path.resolve().parts
    owner = OWNER_PACKAGE.parts
    return any(
        parts[index : index + len(owner)] == owner for index in range(len(parts) - len(owner) + 1)
    )


def _under_hidden_dir(path: Path, root: Path) -> bool:
    """Whether a directory component of `path` below `root` is hidden.

    Args:
        path: The file being considered.
        root: The scan root.

    Returns:
        (bool) True when any directory between `root` and the file starts with `.`.
    """
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    return any(part.startswith(".") for part in relative.parts[:-1])


def _scan(
    root: Path,
    symbols: frozenset[str],
    module: str | None,
    rule: str,
    exempt_owner: bool,
    exclude: Iterable[Path],
) -> list[StaticViolation]:
    """Scan a tree for references to a symbol set and an optional import module.

    Args:
        root: Directory to scan recursively.
        symbols: Symbols whose reference is a violation.
        module: Import module whose import is a violation, or None.
        rule: Rule label for the emitted violations.
        exempt_owner: Whether files under the owning tree are skipped.
        exclude: Directories to skip explicitly (fixture corpora pass their own).

    Returns:
        (list[StaticViolation]) Findings, sorted by path and line.
    """
    excluded = tuple(directory.resolve() for directory in exclude)
    violations: list[StaticViolation] = []
    for path in sorted(root.rglob("*.py")):
        if _under_hidden_dir(path, root):
            continue
        resolved = path.resolve()
        if any(directory in resolved.parents for directory in excluded):
            continue
        if exempt_owner and _is_owned(path):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        visitor = _SymbolVisitor(path, symbols, module, rule)
        visitor.visit(tree)
        violations.extend(visitor.violations)
    return sorted(violations, key=lambda item: (str(item.path), item.line))


def find_producer_can_access(
    root: Path,
    exclude: Iterable[Path] = (),
) -> list[StaticViolation]:
    """Find producer code reaching for the CAN handle (acceptance ⑥).

    The owning actuation tree is exempt — it is where the handle legitimately
    lives. Every other reference to the CAN-writer module or its write symbols is a
    finding.

    Args:
        root: Directory to scan recursively.
        exclude: Directories to skip explicitly.

    Returns:
        (list[StaticViolation]) Offending references, sorted by path and line.
    """
    return _scan(
        root=root,
        symbols=CAN_HANDLE_SYMBOLS,
        module=CAN_HANDLE_MODULE,
        rule="producer reaches for the CAN handle",
        exempt_owner=True,
        exclude=exclude,
    )


def find_disable_torque(
    root: Path,
    exclude: Iterable[Path] = (),
) -> list[StaticViolation]:
    """Find any `disable_torque` reference in the stop path (acceptance ⑦).

    Unlike the CAN-access scan, the owning tree is NOT exempt: the whole point is
    that the stop path — which lives in the owning tree — must not contain the
    symbol.

    Args:
        root: Directory to scan recursively.
        exclude: Directories to skip explicitly.

    Returns:
        (list[StaticViolation]) Offending references, sorted by path and line.
    """
    return _scan(
        root=root,
        symbols=frozenset({DISABLE_TORQUE_SYMBOL}),
        module=None,
        rule="disable_torque in the stop path",
        exempt_owner=False,
        exclude=exclude,
    )
