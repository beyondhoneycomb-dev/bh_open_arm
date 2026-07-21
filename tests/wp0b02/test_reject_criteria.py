"""Acceptance ③ — bitrate ≠ 1000000, dbitrate ≠ 5000000, and BUS-OFF each reject.

Each fixture isolates one criterion so the rejection is attributable: the bitrate fixture
fails only on bitrate, the dbitrate fixture only on dbitrate, the bus-off fixture only on
state. That the sole mismatch is the intended one proves the validator checks that
specific criterion rather than rejecting for an unrelated reason.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.can.link import parse_link_show, validate_link

_CORPUS = Path(__file__).resolve().parent / "fixtures" / "corpus"


@pytest.mark.parametrize(
    ("filename", "field"),
    [
        ("bitrate_mismatch.txt", "bitrate"),
        ("dbitrate_mismatch.txt", "dbitrate"),
        ("bus_off.txt", "state"),
    ],
)
def test_single_criterion_rejection(filename: str, field: str) -> None:
    """Each fixture rejects, and on exactly the one criterion it isolates."""
    state = parse_link_show((_CORPUS / filename).read_text(encoding="utf-8"), "can0")
    verdict = validate_link(state)

    assert not verdict.ok
    assert [mismatch.field for mismatch in verdict.mismatches] == [field]
