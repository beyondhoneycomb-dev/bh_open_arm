"""Acceptance ④ — an unrecognized format raises, never silently passes (5 variants).

Five format-variant fixtures each break recognition a different way: empty output, a
non-CAN interface, a truncated dump, garbage text, and a CAN line missing its state
value. Every one must raise `UnrecognizedLinkFormatError` — a silent default on an unknown
format is the exact failure FR-SYS-006 forbids.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.can.link import UnrecognizedLinkFormatError, parse_link_show

_VARIANTS = Path(__file__).resolve().parent / "fixtures" / "variants"
_FILES = ["empty.txt", "ethernet.txt", "truncated.txt", "garbage.txt", "no_state_value.txt"]


def test_five_variant_fixtures_present() -> None:
    """The acceptance names five variants; the directory holds exactly those."""
    assert sorted(path.name for path in _VARIANTS.glob("*.txt")) == sorted(_FILES)


@pytest.mark.parametrize("filename", _FILES)
def test_unknown_format_raises_never_silently_passes(filename: str) -> None:
    """An unrecognizable format is an explicit error, not a coincidental struct."""
    with pytest.raises(UnrecognizedLinkFormatError):
        parse_link_show((_VARIANTS / filename).read_text(encoding="utf-8"), "can0")
