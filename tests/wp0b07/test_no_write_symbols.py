"""Acceptance ⑧ — the read-only contract: no write path anywhere in the tree.

Static (AST) proof, plus a violation fixture proving the scan actually bites so a
green result means "no write path", not "the scan never fires".
"""

from __future__ import annotations

from pathlib import Path

from backend.can.rid.staticcheck import find_write_symbols

_RID_TREE = Path(__file__).resolve().parents[2] / "backend" / "can" / "rid"
_VIOLATION_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "write_symbol_violation.py"


def test_product_tree_has_no_write_symbols() -> None:
    violations = find_write_symbols(_RID_TREE)
    assert violations == [], "\n".join(str(v) for v in violations)


def test_scan_bites_on_a_real_violation() -> None:
    violations = find_write_symbols(_VIOLATION_FIXTURE)
    assert violations, "the write-symbol scan failed to flag a deliberate violation"
    symbols = {v.symbol for v in violations}
    # Both a forbidden name and a forbidden command byte must be caught.
    assert any("set_zero" in s.lower() for s in symbols)
    assert any("write_param" in s.lower() for s in symbols)
    assert "0x55" in symbols
    assert "0xFE" in symbols


def test_scan_covers_every_module_in_the_tree() -> None:
    # Guard against the scan silently skipping files: it must visit every module,
    # so pointing it at the whole tree and at each file must agree on emptiness.
    modules = [p for p in _RID_TREE.rglob("*.py") if "__pycache__" not in p.parts]
    assert modules, "no modules found to scan"
    for module in modules:
        assert find_write_symbols(module) == [], f"unexpected write symbol in {module}"
