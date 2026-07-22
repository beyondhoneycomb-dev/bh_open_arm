"""Static ban on a consuming 3A schema restating a frozen primitive.

`02b` §5.2 WP-3A-00 ② makes this a build-blocking rule: `CTR-CAM`..`CTR-REC`
consume the six primitives by importing them from `contracts.prim`, and a
consumer that *defines* one — its own `CameraSlotKey`, its own `CLOCK_SOURCE`,
its own `TimestampDomain` — has forked the contract. The named example is a CAP
schema that declares its own timestamp domain; this scan is what makes that fail.

The distinction the scan draws is definition vs consumption. A top-level
`from contracts.prim import CameraSlotKey` binds the name by *import* and is the
sanctioned path. A top-level `class CameraSlotKey` or `CLOCK_SOURCE = ...` binds
it by *definition* and is the fork. Only module-level definitions are flagged: a
local variable that happens to share a reserved name inside some function is not
a contract, so nesting is not walked.

This is machinery, not the contract: it is `EXCLUSIVE`, not `CONTRACT_FROZEN`, so
the reserved set can grow as consumers land without moving the `CTR-PRIM@v1`
frozen hash. The reserved names themselves live in the frozen `schema.py`.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from contracts.prim.schema import RESERVED_PRIMITIVE_SYMBOLS


@dataclass(frozen=True)
class Redefinition:
    """One frozen-primitive name a consumer defined instead of importing.

    Attributes:
        path: File the redefinition was found in.
        line: 1-indexed line of the defining statement.
        symbol: The reserved primitive name that was redefined.
        kind: The Python construct that redefined it (`class`, `def`, `assign`).
    """

    path: str
    line: int
    symbol: str
    kind: str


def _module_body(source: str, filename: str) -> list[ast.stmt]:
    """Parse source and return its top-level statements.

    Args:
        source: Python source text.
        filename: Path used in syntax-error messages.

    Returns:
        (list[ast.stmt]) The module's top-level body.
    """
    return ast.parse(source, filename=filename).body


def _assigned_names(target: ast.expr) -> list[str]:
    """Return the plain names an assignment target binds.

    Tuple/list targets bind several names at once; only bare `Name` targets are
    reserved-symbol candidates, so attribute and subscript targets yield nothing.

    Args:
        target: An assignment target expression.

    Returns:
        (list[str]) Bound bare names.
    """
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, ast.Tuple | ast.List):
        names: list[str] = []
        for element in target.elts:
            names.extend(_assigned_names(element))
        return names
    return []


def scan_module(path: Path) -> list[Redefinition]:
    """Find frozen-primitive names a single module defines rather than imports.

    Args:
        path: Python file to scan (a consuming 3A schema module).

    Returns:
        (list[Redefinition]) One entry per module-level definition of a reserved
            name, in source order.
    """
    hits: list[Redefinition] = []
    for node in _module_body(path.read_text(encoding="utf-8"), str(path)):
        if isinstance(node, ast.ClassDef) and node.name in RESERVED_PRIMITIVE_SYMBOLS:
            hits.append(Redefinition(str(path), node.lineno, node.name, "class"))
        elif (
            isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            and node.name in RESERVED_PRIMITIVE_SYMBOLS
        ):
            hits.append(Redefinition(str(path), node.lineno, node.name, "def"))
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                for name in _assigned_names(target):
                    if name in RESERVED_PRIMITIVE_SYMBOLS:
                        hits.append(Redefinition(str(path), node.lineno, name, "assign"))
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id in RESERVED_PRIMITIVE_SYMBOLS
        ):
            hits.append(Redefinition(str(path), node.lineno, node.target.id, "assign"))
    return hits


def check_no_redefinition(paths: list[Path]) -> list[Redefinition]:
    """Scan several consuming modules for frozen-primitive redefinitions.

    Args:
        paths: Python files to scan.

    Returns:
        (list[Redefinition]) Every redefinition found, in path then source order.
    """
    hits: list[Redefinition] = []
    for path in sorted(paths):
        hits.extend(scan_module(path))
    return hits
