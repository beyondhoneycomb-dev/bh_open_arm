"""Table-reading behaviour that the corpus actually exercises.

Each test here corresponds to a way the corpus broke a naive reader. They are
regression tests for real defects, not illustrations of the API.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from registry.ingest.markdown import find_pipe_defects, plain_text, read_sections, split_row

PLAN_DIR = Path(__file__).resolve().parents[2] / "docs" / "plan"
SPEC_DIR = Path(__file__).resolve().parents[2] / "docs" / "spec"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("`registry/schema/**` (**`EXCLUSIVE`**)", "registry/schema/** (EXCLUSIVE)"),
        ("`ops/cancel/**`, `ops/launch/**`", "ops/cancel/**, ops/launch/**"),
        ("**WP-BOOT-01**", "WP-BOOT-01"),
        ("`send_action()` 오버라이드", "send_action() 오버라이드"),
        ("`{job_id, config_snapshot}`", "{job_id, config_snapshot}"),
        ("a **bold** and `code` mix", "a bold and code mix"),
    ],
)
def test_markup_stripping_preserves_literals(raw: str, expected: str) -> None:
    """Glob wildcards and snake_case survive; emphasis does not."""
    assert plain_text(raw) == expected


def test_glob_wildcard_is_not_read_as_emphasis() -> None:
    """A `**` inside a code span is a glob, not bold.

    Deleting it turns an owned subtree into an owned directory, which voids
    every ownership-overlap check built on the result.
    """
    assert plain_text("`backend/actuation/**`").endswith("/**")


def test_underscore_is_never_emphasis() -> None:
    """The corpus holds 449 snake_case identifiers against one italic span."""
    assert plain_text("`normalization_hash`") == "normalization_hash"


def test_html_break_becomes_a_space() -> None:
    """Gluing clauses together fabricates tokens the document never had."""
    assert plain_text("finish-step<br/>latch-to-hold") == "finish-step latch-to-hold"


def test_unescaped_pipe_in_code_span_does_not_split_the_cell() -> None:
    """A malformed row is recovered rather than dropped.

    Dropping it loses a declared requirement and then reports that requirement
    as an uncovered gap — a false finding produced by the reader itself.
    """
    cells = split_row("| FR-CAM-002 | text | M | `find-cameras opencv|realsense` | [확정] |")
    assert len(cells) == 5
    assert cells[3] == "`find-cameras opencv|realsense`"


def test_escaped_pipe_is_preserved_as_content() -> None:
    """`\\|` is the correct way to write a literal pipe and must survive."""
    assert split_row(r"| a | b \| c |") == ["a", "b | c"]


def test_ragged_rows_are_dropped_rather_than_padded() -> None:
    """Padding a short row invents cell values that were never written."""
    document = "| A | B | C |\n|---|---|---|\n| 1 | 2 |\n| 3 | 4 | 5 |\n"
    path = Path(__file__).parent / "_ragged.md"
    path.write_text(document, encoding="utf-8")
    try:
        table = read_sections(path)[0].tables[0]
        assert table.rows == (("3", "4", "5"),)
    finally:
        path.unlink()


def test_exact_column_match_rejects_a_mentioning_column() -> None:
    """ "소유 WP" must not be mistaken for the "WP" definition column."""
    document = "| 소유 WP | 무엇 |\n|---|---|\n| WP-1-01 | x |\n"
    path = Path(__file__).parent / "_mention.md"
    path.write_text(document, encoding="utf-8")
    try:
        table = read_sections(path)[0].tables[0]
        assert table.exact_column_index("WP") is None
        assert table.column_index("WP") == 0
    finally:
        path.unlink()


def test_corpus_pipe_defects_are_located_not_hidden() -> None:
    """The recovery must not silence the underlying document defect."""
    defects = [
        f"{path.name}:{line}"
        for directory in (SPEC_DIR, PLAN_DIR)
        for path in sorted(directory.glob("*.md"))
        for line, _ in find_pipe_defects(path)
    ]
    assert defects, "recovery is only acceptable while the defects stay reportable"
    assert "06-카메라-서브시스템.md:314" in defects
