"""CG-4A-03d (static) — zero paths mint a clearance without the three-way decision.

`02c` §1.3 ④ requires proving by STATIC check that no path starts training without
presenting the three-way choice. The gate makes this checkable by construction: a
`TrainingClearance` is the token a caller needs, and `clear_for_training` is the only
function allowed to mint one — and only past its completeness raise. This test parses
every source file the degenerate band owns and proves that property:

  1. every `TrainingClearance(...)` construction is lexically inside
     `clear_for_training` (no other mint site — no bypass);
  2. `clear_for_training` contains a `raise` (the undecided/blocked path exists),
     so the single mint site is genuinely gated, not an unconditional return.

Structural limit (stated): this proves the band exposes no bypass. It cannot force a
future WP that owns the `lerobot-train` launch path (WP-4A-01) to demand the token —
this band must not edit that path — so the guarantee is scoped to callers routing
through the gate.
"""

from __future__ import annotations

import ast
from pathlib import Path

_PACKAGE_DIR = Path(__file__).resolve().parents[2] / "backend" / "training" / "degenerate"
_TOKEN = "TrainingClearance"
_MINT_SITE = "clear_for_training"


def _is_token_construction(node: ast.AST) -> bool:
    """Whether an AST node constructs a `TrainingClearance`."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == _TOKEN
    if isinstance(func, ast.Attribute):
        return func.attr == _TOKEN
    return False


class _MintSiteVisitor(ast.NodeVisitor):
    """Records the enclosing function name of every `TrainingClearance` construction.

    A module-level construction (outside any function) is recorded with an empty
    enclosing name, which fails the single-mint-site assertion as loudly as a
    construction in the wrong function would.
    """

    def __init__(self) -> None:
        self.mStack: list[str] = []
        self.mSites: list[str] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802 - ast visitor API
        self.mStack.append(node.name)
        self.generic_visit(node)
        self.mStack.pop()

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802 - ast visitor API
        if _is_token_construction(node):
            self.mSites.append(self.mStack[-1] if self.mStack else "")
        self.generic_visit(node)


def _sources() -> list[Path]:
    return sorted(_PACKAGE_DIR.glob("*.py"))


def test_clearance_is_minted_only_inside_the_gate() -> None:
    sites: list[str] = []
    for source in _sources():
        visitor = _MintSiteVisitor()
        visitor.visit(ast.parse(source.read_text(encoding="utf-8"), filename=str(source)))
        sites.extend(visitor.mSites)

    assert sites, "the clearance token is never constructed; the gate does not mint it"
    # Every construction is inside clear_for_training — no bypass mint site anywhere.
    assert all(site == _MINT_SITE for site in sites), (
        f"TrainingClearance is constructed outside {_MINT_SITE}: {sites}"
    )


def test_the_mint_site_is_gated_by_a_raise() -> None:
    gate_source = _PACKAGE_DIR / "gate.py"
    tree = ast.parse(gate_source.read_text(encoding="utf-8"), filename=str(gate_source))
    gate_fn = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == _MINT_SITE
    )
    raises = [node for node in ast.walk(gate_fn) if isinstance(node, ast.Raise)]
    assert raises, f"{_MINT_SITE} has no raise; its single mint site would be unconditional"
