"""Static proof that the RID harness holds no write path (acceptance ⑧).

The read-only contract is stated as an absence — "write (`0x55`), `set_zero`
(`0xFE`), `change_id`, `change_baud`, `clear_error` paths are not present" — and an
absence can only be checked honestly by reading every line, because a runtime test
proves only the paths it happened to run. So this is an AST scan over the whole
`backend/can/rid/**` tree, and it ships with a violation fixture proving the scan
actually bites.

The scan reads identifiers (names, attributes, defs, arguments) and integer
literals, never string or docstring text — a docstring that spells out the banned
verbs to document the ban is prose, not a code path, exactly as the value bytes of
a dump fixture that happen to equal `0x55` are data, not a write command. Only
`staticcheck.py` itself is exempt, because it must hold the banned tokens as its
needle table.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

# Identifier fragments that name a write path (`03` §2.6 / §4.1). A substring match
# catches wrapped forms (`create_set_zero_command`, `pack_write_param_data`).
FORBIDDEN_NAME_TOKENS: tuple[str, ...] = (
    "set_zero",
    "change_id",
    "change_baud",
    "clear_error",
    "write_param",
)

# Command bytes that, appearing as an integer literal, mean a write frame is being
# built: `0x55` is Write Param, `0xFE` is set-zero (`03` §2.5).
FORBIDDEN_COMMAND_BYTES: frozenset[int] = frozenset({0x55, 0xFE})

# This detector holds the banned tokens above as data, so it must not scan itself.
SELF_EXEMPT_FILENAME = "staticcheck.py"


@dataclass(frozen=True)
class StaticViolation:
    """A write-path construct found where the contract forbids one.

    Attributes:
        path: File the construct was found in.
        line: 1-indexed line.
        symbol: The offending identifier or literal.
        rule: Which part of the read-only contract it breaks.
    """

    path: Path
    line: int
    symbol: str
    rule: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.rule}: {self.symbol}"


class _WriteSymbolVisitor(ast.NodeVisitor):
    """Collect write-path identifiers and command-byte literals in one module."""

    def __init__(self) -> None:
        self.findings: list[tuple[int, str]] = []

    def _check_name(self, name: str, lineno: int) -> None:
        """Record a finding if an identifier names a write path.

        Args:
            name: The identifier text.
            lineno: The line it appears on.
        """
        lowered = name.lower()
        for token in FORBIDDEN_NAME_TOKENS:
            if token in lowered:
                self.findings.append((lineno, name))
                break

    def visit_Name(self, node: ast.Name) -> None:  # noqa: N802  (ast visitor naming)
        self._check_name(node.id, node.lineno)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802
        self._check_name(node.attr, node.lineno)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._check_name(node.name, node.lineno)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self._check_name(node.name, node.lineno)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        self._check_name(node.name, node.lineno)
        self.generic_visit(node)

    def visit_arg(self, node: ast.arg) -> None:
        self._check_name(node.arg, node.lineno)
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:  # noqa: N802
        # `bool` is an `int` subclass; a `True`/`False` literal is not a byte.
        if (
            isinstance(node.value, int)
            and not isinstance(node.value, bool)
            and node.value in FORBIDDEN_COMMAND_BYTES
        ):
            self.findings.append((node.lineno, f"0x{node.value:02X}"))
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


def find_write_symbols(root: Path) -> list[StaticViolation]:
    """Find any write-path identifier or command-byte literal under a tree.

    A non-empty result means the read-only contract (acceptance ⑧) is broken: some
    module names a write verb or builds a Write-Param / set-zero frame. The scan
    skips only itself, since it must carry the banned tokens as its needle table.

    Args:
        root: Directory (or file) to scan.

    Returns:
        (list[StaticViolation]) One finding per offending site, sorted by path
        and line; empty when the tree is write-free.
    """
    violations: list[StaticViolation] = []
    for path in _iter_python(root):
        if path.name == SELF_EXEMPT_FILENAME:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        visitor = _WriteSymbolVisitor()
        visitor.visit(tree)
        violations.extend(
            StaticViolation(
                path=path,
                line=line,
                symbol=symbol,
                rule="write path present in a read-only harness",
            )
            for line, symbol in visitor.findings
        )
    return sorted(violations, key=lambda item: (str(item.path), item.line))
