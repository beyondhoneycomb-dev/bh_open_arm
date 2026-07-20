"""Mechanical GitHub-flavoured-Markdown table reader for the planning corpus.

Scope: this module knows about pipe tables and nothing about work packages. It
exists because three planning documents encode the same records in three
different table layouts, and the layout-specific extractors in `catalog.py`
need a shared, dependency-free way to get at cells.

Cells are returned with their inline markup intact. Callers decide what to
strip, because `**bold**` and `` `code` `` are load-bearing in some columns
(a WP id is always in one or the other) and noise in others.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_SEPARATOR_ROW = re.compile(r"^\|(?:\s*:?-{3,}:?\s*\|)+\s*$")
_HTML_BREAK = re.compile(r"<br\s*/?>", re.IGNORECASE)
_CODE_SPAN = re.compile(r"`+")


@dataclass(frozen=True)
class Table:
    """One pipe table lifted out of a Markdown document.

    Attributes:
        header: Cell texts of the header row, markup intact.
        rows: Data rows, each the same length as `header`.
        header_line: 1-indexed line number of the header row in the source file.
        source: Path of the document the table came from.
    """

    header: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    header_line: int
    source: Path

    def exact_column_index(self, label: str) -> int | None:
        """Return the index of the header cell whose plain text equals `label`.

        Distinct from `column_index` because several catalog tables carry both
        a "WP" column and a column merely *mentioning* work packages ("소유 WP",
        "백엔드 WP (실재 ID)"). Containment matching picks the wrong one and the
        parser then reads a citation as a definition.

        Args:
            label: Exact header text to match.

        Returns:
            (int | None) Index of the matching column, or None if absent.
        """
        for index, cell in enumerate(self.header):
            if plain_text(cell) == label:
                return index
        return None

    def column_index(self, *candidates: str) -> int | None:
        """Return the index of the first header cell matching any candidate.

        Matching is on the plain-text form, so `**입력**` matches "입력".
        Comparison is containment, not equality, because several headers carry
        a parenthetical qualifier such as "수용 게이트 (검증가능)".

        Args:
            candidates: Header labels to look for, in priority order.

        Returns:
            (int | None) Index of the matching column, or None if absent.
        """
        plain = [plain_text(cell) for cell in self.header]
        for candidate in candidates:
            for index, cell in enumerate(plain):
                if candidate in cell:
                    return index
        return None


@dataclass
class Section:
    """A heading and the tables that appear under it, before the next heading.

    Attributes:
        level: Number of leading '#' characters.
        title: Heading text with the '#' markers stripped.
        line: 1-indexed line number of the heading.
        tables: Tables occurring under this heading.
    """

    level: int
    title: str
    line: int
    tables: list[Table] = field(default_factory=list)


def plain_text(cell: str) -> str:
    """Strip inline Markdown markup while preserving code-span contents verbatim.

    Markup is removed structurally, not by deleting characters, because both
    characters that would be deleted are load-bearing data in this corpus:

    - `*` is the glob wildcard in ownership paths (`registry/schema/**`).
      Deleting it turns an owned subtree into an owned directory and silently
      voids every ownership-overlap check built on the result.
    - `_` is in 449 distinct snake_case identifiers (`send_action`,
      `normalization_hash`) against exactly one genuine `_italic_` span.

    The corpus writes literal values inside backticks and emphasis outside
    them, so honouring the code-span boundary separates the two cases exactly.
    `<br/>` becomes a space, not nothing: catalog cells use it between clauses,
    and gluing those clauses together fabricates tokens the document never had.

    Args:
        cell: Raw cell text.

    Returns:
        (str) Cell text with emphasis markers removed and code spans intact.
    """
    without_breaks = _HTML_BREAK.sub(" ", cell)

    pieces: list[str] = []
    position = 0
    for fence in _CODE_SPAN.finditer(without_breaks):
        if fence.start() < position:
            continue
        closing = without_breaks.find(fence.group(), fence.end())
        if closing == -1:
            continue
        pieces.append(without_breaks[position : fence.start()].replace("*", ""))
        pieces.append(without_breaks[fence.end() : closing])
        position = closing + len(fence.group())
    pieces.append(without_breaks[position:].replace("*", ""))

    return " ".join("".join(pieces).split())


def split_row(line: str) -> list[str]:
    """Split one pipe-table line into its cells.

    Two kinds of pipe survive the split as literal text:

    - An escaped pipe (`\\|`), which is the correct way to write one.
    - An *unescaped* pipe inside a code span, which is malformed per the
      GFM table spec but occurs in the corpus (`` `opencv|realsense` ``).
      Splitting there yields a row one cell too wide, and a width mismatch
      makes the row look ragged and get discarded — losing a declared
      requirement while reporting it as an uncovered gap. Cells are rejoined
      until their backticks balance, so the span is reconstructed rather than
      the row dropped. `find_pipe_defects` reports the affected rows.

    Args:
        line: A single source line beginning with '|'.

    Returns:
        (list) Cell texts, leading and trailing empties removed.
    """
    placeholder = "\x00"
    protected = line.strip().replace("\\|", placeholder)
    cells = [cell.strip().replace(placeholder, "|") for cell in protected.split("|")]
    if cells and not cells[0]:
        cells.pop(0)
    if cells and not cells[-1]:
        cells.pop()

    rejoined: list[str] = []
    for cell in cells:
        if rejoined and rejoined[-1].count("`") % 2:
            rejoined[-1] = f"{rejoined[-1]}|{cell}"
        else:
            rejoined.append(cell)
    return rejoined


def find_pipe_defects(path: Path) -> list[tuple[int, str]]:
    """Locate table rows holding an unescaped pipe inside a code span.

    These rows render with shifted columns in any conforming Markdown viewer,
    so they are document defects rather than parser concerns. `split_row`
    recovers the data; this reports the source locations so the defect can be
    fixed rather than permanently worked around.

    Args:
        path: Markdown file to scan.

    Returns:
        (list) `(line_number, line)` pairs, 1-indexed.
    """
    defects: list[tuple[int, str]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.lstrip().startswith("|"):
            continue
        naive = line.strip().replace("\\|", "\x00").split("|")
        if len(naive) != len(split_row(line)) + 2:
            defects.append((number, line))
    return defects


def read_sections(path: Path) -> list[Section]:
    """Parse a Markdown file into headings with their tables attached.

    A table is recognised by a header line followed immediately by a separator
    row. Rows whose cell count differs from the header are dropped, because a
    ragged row means the document is malformed at that point and silently
    padding it would invent data.

    Args:
        path: Markdown file to read.

    Returns:
        (list) Sections in document order. Tables appearing before the first
        heading are attached to a synthetic level-0 section.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    sections = [Section(level=0, title=path.stem, line=0)]

    index = 0
    while index < len(lines):
        line = lines[index]

        heading = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading:
            sections.append(
                Section(level=len(heading.group(1)), title=heading.group(2).strip(), line=index + 1)
            )
            index += 1
            continue

        is_table_head = (
            line.lstrip().startswith("|")
            and index + 1 < len(lines)
            and _SEPARATOR_ROW.match(lines[index + 1].strip())
        )
        if not is_table_head:
            index += 1
            continue

        header = tuple(split_row(line))
        rows: list[tuple[str, ...]] = []
        cursor = index + 2
        while cursor < len(lines) and lines[cursor].lstrip().startswith("|"):
            cells = split_row(lines[cursor])
            if len(cells) == len(header):
                rows.append(tuple(cells))
            cursor += 1

        sections[-1].tables.append(
            Table(header=header, rows=tuple(rows), header_line=index + 1, source=path)
        )
        index = cursor

    return sections


def all_tables(path: Path) -> list[Table]:
    """Return every table in a document, ignoring heading structure.

    Args:
        path: Markdown file to read.

    Returns:
        (list) Tables in document order.
    """
    return [table for section in read_sections(path) for table in section.tables]
