"""Static-check acceptance: inline code literals in product source are caught.

Acceptance ⑥ (inline-literal emission -> static reject) and ⑦ (CI half:
unregistered-code emission -> static reject). Fixture sources are written to a
temp path so no committed file carries a banned literal that a tree-wide scan
would later trip on.
"""

from __future__ import annotations

from pathlib import Path

from contracts.errors.registry import REGISTRY
from contracts.errors.static_check import scan_source, unregistered_hits

_IMPORT = "from contracts.errors import codes, make_error\n"
_INLINE_LITERAL_EMIT = _IMPORT + 'raise make_error("OA-CAN-003")\n'
_UNREGISTERED_EMIT = _IMPORT + 'raise make_error("OA-ZZZ-999")\n'
_SYMBOL_EMIT = _IMPORT + "raise make_error(codes.OA_CAN_003)\n"


def _write(tmp_path: Path, name: str, source: str) -> Path:
    """Write a fixture source file and return its path."""
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return path


def test_inline_literal_is_flagged(tmp_path: Path) -> None:
    """A `make_error("OA-CAN-003")` literal is caught (acceptance ⑥)."""
    path = _write(tmp_path, "inline.py", _INLINE_LITERAL_EMIT)
    hits = scan_source([path])
    assert [hit.code for hit in hits] == ["OA-CAN-003"]


def test_symbol_reference_is_clean(tmp_path: Path) -> None:
    """The sanctioned symbol form produces no hit (no over-blocking)."""
    path = _write(tmp_path, "clean.py", _SYMBOL_EMIT)
    assert scan_source([path]) == []


def test_unregistered_literal_is_distinguished(tmp_path: Path) -> None:
    """An unregistered literal is both a literal ban and an unregistered hit (⑦)."""
    known = set(REGISTRY.codes)
    registered = _write(tmp_path, "registered.py", _INLINE_LITERAL_EMIT)
    unregistered = _write(tmp_path, "unregistered.py", _UNREGISTERED_EMIT)

    hits = scan_source([registered, unregistered], known_codes=known)
    unresolved = unregistered_hits(hits)
    assert {hit.code for hit in unresolved} == {"OA-ZZZ-999"}
    # The registered literal is still a literal-ban hit, just not an unregistered one.
    assert {hit.code for hit in hits} == {"OA-CAN-003", "OA-ZZZ-999"}
