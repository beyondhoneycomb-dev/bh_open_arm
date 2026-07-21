"""Static ban on emitting a code as an inline literal instead of a registry symbol.

The registry is canon and emission points are consumers (14 §2.10): product code
must name a code through `contracts.errors.codes.OA_*`, never as a bare string
`"OA-CAN-003"`. This AST scan catches the literal form (acceptance ⑥) and, when
given the registry, the emission of a code no row backs (acceptance ⑦, CI half).

It scans only product source. The registry data module, this scanner and the test
fixtures legitimately contain code strings, so callers exclude those paths — a
scanner that fired on the registry defining its own codes would be unusable.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

# A code literal anywhere in an expression is the ban's target; matching the whole
# string (not a substring) keeps prose like "OA codes" from tripping it.
_CODE_LITERAL = re.compile(r"^OA-[A-Z]+-[0-9A-F]{3}$")


@dataclass(frozen=True)
class LiteralHit:
    """One inline code literal found in product source.

    Attributes:
        path: File it was found in.
        line: 1-indexed line.
        code: The literal code string.
        registered: Whether that code exists in the registry (when one was given).
    """

    path: str
    line: int
    code: str
    registered: bool


def scan_source(paths: list[Path], known_codes: set[str] | None = None) -> list[LiteralHit]:
    """Find inline OA-* code literals in the given Python sources.

    Args:
        paths: Python files to scan (callers exclude the registry and fixtures).
        known_codes: When given, each hit is tagged registered/unregistered so a
            caller can reject unregistered emission (⑦) distinctly from the
            literal ban (⑥). When None, every hit is a literal-ban violation.

    Returns:
        (list[LiteralHit]) One hit per inline code literal, in path/line order.
    """
    hits: list[LiteralHit] = []
    for path in sorted(paths):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if not _CODE_LITERAL.match(node.value):
                continue
            registered = known_codes is None or node.value in known_codes
            hits.append(
                LiteralHit(
                    path=str(path),
                    line=node.lineno,
                    code=node.value,
                    registered=registered,
                )
            )
    return hits


def unregistered_hits(hits: list[LiteralHit]) -> list[LiteralHit]:
    """Filter to literals naming a code no registry row backs.

    Args:
        hits: Hits from `scan_source` called with `known_codes`.

    Returns:
        (list[LiteralHit]) Hits whose code is unregistered.
    """
    return [hit for hit in hits if not hit.registered]
