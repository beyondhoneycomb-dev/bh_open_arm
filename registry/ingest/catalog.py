"""Extract work-package definitions from the four planning catalogs.

The catalogs (`docs/plan/02a`..`02d`) are the sole issuing authority for
`WP-*` ids (`00` §8.2). This module reads them and nothing else writes ids.

Three table layouts encode the same record, one per document family, so there
are three extractors rather than one configurable one:

- `02a`   a single 9-column row per work package.
- `02b`, `02d`   the record split across a 6-column table and a 5-column
  table, joined on the work-package id.
- `02c`   one vertical `| 항목 | 내용 |` card per work package, with the id in
  the enclosing heading rather than in a cell.

Ownership of the direction matters: prose is the input *only* while
bootstrapping. Once `registry/traceability.yaml` exists it becomes canonical
and the prose is a view of it (`05` §0.1), so this module is a seeding tool,
not a runtime dependency of the registry.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from registry.ingest.markdown import Section, Table, plain_text, read_sections

# The `G<n>` suffix form is the band-local GUI liaison package (`WP-4A-G1`,
# `WP-4C-G1`); `S<nn>` is the per-screen GUI form (`WP-G-S13`).
WP_ID = re.compile(r"\bWP-(?:BOOT|N1|ENV|0A|0B|0C|OPS|[1-5][A-D]?|G)-[SG]?\d{1,2}[a-z]?\b")
REQ_ID = re.compile(r"\b(?:FR|NFR)-[A-Z]{2,4}-\d{3}\b")
PG_ID = re.compile(r"\bPG-[A-Z0-9]+-\d{3}[ab]?\b")
CG_ID = re.compile(r"\bCG-[A-Z0-9]+-\d{2}[a-z]\b")
CONTRACT_ID = re.compile(r"\bCTR-[A-Z]+@v\d+\b")
SHAPE_TOKEN = re.compile(r"\bSHAPE-(?:CF|IM|IG|MS|HG)\b")
EXEC_CLASS = re.compile(r"\b(?:AI-offline|AI-on-HW|Human-assisted-HW|Human-judgment)\b")
OWNS_CLAUSE = re.compile(r"소유 경로\s*=\s*(.*)$")
# A mode applies to the whole comma-separated group that precedes it, and the
# parenthesis may carry trailing prose ("(GENERATED — 손으로 편집하면 거부)").
OWNS_MODE_GROUP = re.compile(r"\(\s*(EXCLUSIVE|GENERATED|CONTRACT_FROZEN|SHARED_APPEND)[^)]*\)")
OWNS_PATH = re.compile(r"^[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.*-]+)*/?\*{0,2}$")
ENUM_MARKERS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"

_BAND_OF_ID = re.compile(r"^WP-([A-Z0-9]+)-")


@dataclass(frozen=True)
class CatalogEntry:
    """One work package as the catalogs declare it, before axis derivation.

    Text columns are kept whole rather than pre-split. The catalogs mix
    identifiers with justifying prose in the same cell, so the axis derivation
    step extracts ids by pattern and the surrounding prose stays available as
    provenance for the reconciliation report.

    Attributes:
        wp_id: Issued work-package id.
        band: Band token parsed out of the id.
        name: Short name, where the layout supplies one.
        source: Catalog file the definition came from.
        source_line: 1-indexed line of the defining row or heading.
        reqs: Requirement ids cited in the specification column.
        consumes_text: Raw "입력" column.
        produces_text: Raw "산출"/"산출물" column.
        contract_text: Raw interface-contract column.
        acceptance_text: Raw acceptance column, source of derived `CG-*` ids.
        negative_text: Raw negative-branch column.
        exec_classes: Execution-class tokens in declaration order. Length > 1
            means the catalog declared a multi-stage package.
        workflows: Workflow-shape tokens in declaration order. Length > 1 means
            the catalog declared a multi-stage package.
    """

    wp_id: str
    band: str
    name: str
    source: Path
    source_line: int
    reqs: tuple[str, ...]
    consumes_text: str
    produces_text: str
    contract_text: str
    acceptance_text: str
    negative_text: str
    exec_classes: tuple[str, ...]
    workflows: tuple[str, ...]

    @property
    def is_multi_stage(self) -> bool:
        """Whether the catalog declared more than one execution stage.

        The catalogs write multi-stage packages as two tokens in one cell
        (`SHAPE-IM(9) → SHAPE-HG`). A scalar manifest field may hold exactly
        one token, so these must be re-encoded as `phases[]` (`00` §3.2a).
        """
        return len(self.workflows) > 1 or len(self.exec_classes) > 1

    def acceptance_item_count(self) -> int:
        """Count the numbered acceptance items in the acceptance column.

        The count is load-bearing: `CG-*` ids are derived positionally from it
        (`06` §2.4a), so item n becomes suffix letter n. Counting the distinct
        markers present rather than the highest marker seen keeps a document
        typo from silently inventing a gate id.

        Returns:
            (int) Number of distinct enumeration markers found.
        """
        return len({marker for marker in ENUM_MARKERS if marker in self.acceptance_text})

    def derived_cg_ids(self) -> tuple[str, ...]:
        """Derive this work package's acceptance-check ids.

        `CG-<band>-<number><letter>` where letter is the 1-based position of
        the acceptance item (`06` §2.4a). Derivation is the canonical source
        for `02a`/`02b`; `02c`/`02d` also state the ids explicitly and CI-04c
        checks the two agree.

        Returns:
            (tuple) Derived `CG-*` ids in acceptance-item order.
        """
        suffix = self.wp_id[len("WP-") :]
        return tuple(
            f"CG-{suffix}{chr(ord('a') + index)}" for index in range(self.acceptance_item_count())
        )

    def declared_owns(self) -> tuple[tuple[str, str], ...]:
        """Parse `소유 경로 = <glob>[, <glob>]* (<MODE>)` clauses from the contract column.

        The grammar is a sequence of groups: comma-separated paths, then one
        parenthesised mode that applies to all of them. Two properties of the
        corpus make the obvious regex wrong, and both fail silently:

        - Paths contain dots (`registry/traceability.yaml`), so a clause
          terminated at the first `.` truncates the path rather than ending the
          sentence.
        - A mode governs a *group*, not the single path before it, so requiring
          `(MODE)` to follow each path keeps only the last path of each group.

        Either mistake yields a shorter `owns` list and no error, which makes
        the ownership-overlap checks vacuous — they pass because there is
        nothing left to overlap.

        Only `02a` states ownership inline this way. Other packages draw it from
        the map in `06` §3.2, which the caller resolves.

        Returns:
            (tuple) `(glob, mode)` pairs declared in this row, in source order.
        """
        clause = OWNS_CLAUSE.search(self.contract_text)
        if not clause:
            return ()

        owned: list[tuple[str, str]] = []
        position = 0
        text = clause.group(1)
        for group in OWNS_MODE_GROUP.finditer(text):
            for candidate in text[position : group.start()].split(","):
                path = candidate.strip().rstrip(".")
                if path and OWNS_PATH.match(path):
                    owned.append((path, group.group(1)))
            position = group.end()
        return tuple(owned)


def _cell(row: tuple[str, ...], index: int | None) -> str:
    """Return a row cell as plain text, or empty string when the column is absent."""
    return plain_text(row[index]) if index is not None and index < len(row) else ""


def _band(wp_id: str) -> str:
    """Extract the band token from a work-package id."""
    match = _BAND_OF_ID.match(wp_id)
    return match.group(1) if match else ""


def _first(pattern: re.Pattern[str], text: str) -> str:
    """Return the first regex match in text, or empty string."""
    found = pattern.search(text)
    return found.group(0) if found else ""


def _field(fields: dict[str, str], *candidates: str) -> str:
    """Look up a card field by label prefix rather than exact equality.

    Card labels carry parenthetical qualifiers that vary per document — "수용
    게이트 (검증가능)" in `02a`, "수용 게이트 (10항목 각각이 게이트다)" in `02c`.
    Exact matching silently returns empty for both, which reads downstream as
    "this work package declares no acceptance criteria" and is false.

    Args:
        fields: Card label to cell text.
        candidates: Label prefixes to try, in priority order.

    Returns:
        (str) The matching cell text, or empty string when none match.
    """
    for candidate in candidates:
        for label, value in fields.items():
            if label.startswith(candidate):
                return value
    return ""


def _wp_definition_column(table: Table) -> int | None:
    """Return the index of the work-package id column, if this table defines packages.

    A definition table has a column headed exactly "WP" *and* at least one
    column that only a definition supplies. Both halves are needed:

    - Exact "WP" matching rejects tables that merely cite packages through a
      "소유 WP" or "백엔드 WP (실재 ID)" column.
    - The defining-column requirement rejects the screen-route table in `02d`,
      the target-obligation table in `02c`, and the predecessor table in `02b`,
      all of which key on "WP" without defining anything.

    The id column is located rather than assumed to be first, because the
    Wave 1 table in `02a` prefixes an ordinal "순서" column.
    """
    if not table.header:
        return None
    index = table.exact_column_index("WP")
    if index is None:
        return None
    defining = ("입력", "산출", "동결 인터페이스 계약", "수용")
    if not any(table.column_index(label) is not None for label in defining):
        return None
    return index


def _extract_wide(sections: list[Section], path: Path) -> list[CatalogEntry]:
    """Extract from the `02a` layout: one 9-column row per work package."""
    entries: list[CatalogEntry] = []
    for section in sections:
        for table in section.tables:
            wp_column = _wp_definition_column(table)
            if wp_column is None or table.column_index("이름") is None:
                continue
            columns = {
                "name": table.column_index("이름"),
                "spec": table.column_index("명세 영역"),
                "consumes": table.column_index("입력"),
                "produces": table.column_index("산출물", "산출"),
                "contract": table.column_index("인터페이스 계약"),
                "acceptance": table.column_index("수용 게이트", "수용"),
                "exec": table.column_index("클래스"),
                "shape": table.column_index("형상"),
            }
            for offset, row in enumerate(table.rows):
                wp_id = _first(WP_ID, plain_text(row[wp_column]))
                if not wp_id:
                    continue
                acceptance = _cell(row, columns["acceptance"])
                entries.append(
                    CatalogEntry(
                        wp_id=wp_id,
                        band=_band(wp_id),
                        name=_cell(row, columns["name"]),
                        source=path,
                        source_line=table.header_line + 2 + offset,
                        reqs=tuple(dict.fromkeys(REQ_ID.findall(_cell(row, columns["spec"])))),
                        consumes_text=_cell(row, columns["consumes"]),
                        produces_text=_cell(row, columns["produces"]),
                        contract_text=_cell(row, columns["contract"]),
                        acceptance_text=acceptance,
                        negative_text=acceptance,
                        exec_classes=tuple(EXEC_CLASS.findall(_cell(row, columns["exec"]))),
                        workflows=tuple(SHAPE_TOKEN.findall(_cell(row, columns["shape"]))),
                    )
                )
    return entries


def _extract_split(sections: list[Section], path: Path) -> list[CatalogEntry]:
    """Extract from the `02b`/`02d` layout: a 6-column table joined to a 5-column one.

    The two tables are matched on work-package id rather than on position,
    because several waves list them in different orders and a positional join
    would silently pair one package's acceptance criteria with another's.
    """
    definitions: dict[str, tuple[Table, tuple[str, ...], int]] = {}
    contracts: dict[str, tuple[Table, tuple[str, ...]]] = {}

    for section in sections:
        for table in section.tables:
            wp_column = _wp_definition_column(table)
            if wp_column is None:
                continue
            has_negative = table.column_index("음성 분기") is not None
            for offset, row in enumerate(table.rows):
                wp_id = _first(WP_ID, plain_text(row[wp_column]))
                if not wp_id:
                    continue
                if has_negative:
                    contracts[wp_id] = (table, row)
                else:
                    definitions[wp_id] = (table, row, table.header_line + 2 + offset)

    entries: list[CatalogEntry] = []
    for wp_id, (table, row, line) in definitions.items():
        contract_table, contract_row = contracts.get(wp_id, (None, ()))
        acceptance = negative = contract_text = spec_text = ""
        if contract_table is not None:
            acceptance = _cell(contract_row, contract_table.column_index("수용"))
            negative = _cell(contract_row, contract_table.column_index("음성 분기"))
            contract_text = _cell(contract_row, contract_table.column_index("동결 인터페이스 계약"))
            spec_text = _cell(contract_row, contract_table.column_index("명세 근거"))

        entries.append(
            CatalogEntry(
                wp_id=wp_id,
                band=_band(wp_id),
                name=_cell(row, table.column_index("무엇")),
                source=path,
                source_line=line,
                reqs=tuple(dict.fromkeys(REQ_ID.findall(spec_text))),
                consumes_text=_cell(row, table.column_index("입력")),
                produces_text=_cell(row, table.column_index("산출")),
                contract_text=contract_text,
                acceptance_text=acceptance,
                negative_text=negative,
                exec_classes=tuple(
                    EXEC_CLASS.findall(_cell(row, table.column_index("실행클래스")))
                ),
                workflows=tuple(SHAPE_TOKEN.findall(_cell(row, table.column_index("형상")))),
            )
        )
    return entries


def _extract_cards(sections: list[Section], path: Path) -> list[CatalogEntry]:
    """Extract from the `02c` layout: one vertical `| 항목 | 내용 |` card per package.

    The id lives in the enclosing heading, so a card is only claimed when its
    heading names exactly one work package. Headings naming several ids are
    cross-reference sections, not definitions.
    """
    entries: list[CatalogEntry] = []
    for section in sections:
        ids = set(WP_ID.findall(section.title))
        if len(ids) != 1:
            continue
        wp_id = ids.pop()

        fields: dict[str, str] = {}
        for table in section.tables:
            if len(table.header) != 2 or plain_text(table.header[0]) != "항목":
                continue
            for row in table.rows:
                fields[plain_text(row[0])] = plain_text(row[1])
        if not fields:
            continue

        name = section.title.split("—", 1)[-1].strip() if "—" in section.title else section.title
        entries.append(
            CatalogEntry(
                wp_id=wp_id,
                band=_band(wp_id),
                name=name,
                source=path,
                source_line=section.line,
                reqs=tuple(dict.fromkeys(REQ_ID.findall(_field(fields, "명세")))),
                consumes_text=_field(fields, "입력"),
                produces_text=_field(fields, "산출"),
                contract_text=_field(fields, "인터페이스 계약"),
                acceptance_text=_field(fields, "수용 게이트", "수용 검사", "수용"),
                negative_text=_field(fields, "음성 분기"),
                exec_classes=tuple(EXEC_CLASS.findall(_field(fields, "실행 클래스"))),
                workflows=tuple(SHAPE_TOKEN.findall(_field(fields, "워크플로우 형상", "형상"))),
            )
        )
    return entries


def parse_catalog(path: Path) -> list[CatalogEntry]:
    """Extract every work package a single catalog issues.

    All three extractors run. Each recognises its own layout and returns
    nothing for the others, so a catalog that later adopts a second layout is
    covered without changing the dispatch.

    Args:
        path: Catalog Markdown file.

    Returns:
        (list) Entries in document order, one per issued work package.
    """
    sections = read_sections(path)
    found: dict[str, CatalogEntry] = {}
    for extractor in (_extract_wide, _extract_split, _extract_cards):
        for entry in extractor(sections, path):
            found.setdefault(entry.wp_id, entry)
    return sorted(found.values(), key=lambda entry: (entry.source_line, entry.wp_id))


def parse_all(plan_dir: Path) -> list[CatalogEntry]:
    """Extract every work package the four catalogs issue.

    Args:
        plan_dir: Directory holding `02a`..`02d`.

    Returns:
        (list) Entries across all catalogs, sorted by work-package id.

    Raises:
        ValueError: If two catalogs issue the same id. Ids have exactly one
            issuing document (`00` §8.2); a duplicate means the boundary broke
            and picking a winner here would hide it.
    """
    entries: dict[str, CatalogEntry] = {}
    for path in sorted(plan_dir.glob("02[a-d]-*.md")):
        for entry in parse_catalog(path):
            if entry.wp_id in entries:
                first = entries[entry.wp_id]
                raise ValueError(
                    f"{entry.wp_id} issued twice: {first.source.name}:{first.source_line} "
                    f"and {entry.source.name}:{entry.source_line}"
                )
            entries[entry.wp_id] = entry
    return sorted(entries.values(), key=lambda entry: entry.wp_id)
