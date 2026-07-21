"""Extract declared requirements from the specification corpus.

`docs/spec/` is the requirements canon. A requirement exists when it has a row
in a declaration table, not when its id appears somewhere in prose — the
distinction is load-bearing, because the corpus discusses id *formats* in
running text (`00` §5.1 explains why doc 15 uses `NFR-PRF-*` rather than
`NFR-NFR-*`) and a prose scan harvests those illustrations as real ids.

CI-01 as written in `06` §5 specifies exactly such a prose scan. Implementing
it literally would import that illustration into the registry as a phantom
requirement, so this module parses declarations and `registry/checks/ci_01.py`
reports the discrepancy rather than inheriting it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from registry.ingest.catalog import REQ_ID
from registry.ingest.markdown import plain_text, read_sections

__all__ = ["REQ_ID", "Requirement", "find_duplicates", "parse_all", "parse_spec"]

VALID_PRIORITY = ("M", "S", "C")
VALID_TAG = ("확정", "미확인", "결정필요", "신규구현")

# An out-of-vocabulary tag resolves to "미확인" rather than "확정". Both are
# guesses, but they fail in opposite directions: calling an unverified
# requirement confirmed removes scrutiny it never earned, while calling it
# unverified only adds scrutiny it may not need. The original is preserved in
# `raw_tag` and counted in the reconciliation report.
TAG_FALLBACK = "미확인"

_DOC_NUMBER = re.compile(r"^(\d{2})-")
_SECTION_NUMBER = re.compile(r"^(\d+(?:\.\d+)*[a-z]?)\s")
_TAG_MARKER = re.compile(r"\[([^\]]{1,16})\]")


@dataclass(frozen=True)
class Requirement:
    """One requirement as the specification declares it.

    Attributes:
        req_id: Requirement id, e.g. `FR-CAM-002`.
        doc: Two-digit specification document number, e.g. `06`.
        section: Section number the declaring table sits under, e.g. `3.2`.
        priority: Declared priority, normalised to `M`, `S` or `C`.
        raw_priority: Priority cell as written, kept when it does not normalise.
        tag: Declared status, normalised to the four values the schema allows.
        raw_tag: Status marker as written, empty when the row declares none.
        text: Requirement text.
        source: Specification file.
        source_line: 1-indexed line of the declaring row.
    """

    req_id: str
    doc: str
    section: str
    priority: str
    raw_priority: str
    tag: str
    raw_tag: str
    text: str
    source: Path
    source_line: int

    @property
    def spec_ref(self) -> str:
        """Return the `<document>#<section>` reference the registry stores."""
        return f"{self.doc}#{self.section}"

    @property
    def priority_is_valid(self) -> bool:
        """Whether the declared priority is one of the three the schema allows."""
        return self.priority in VALID_PRIORITY

    @property
    def tag_is_declared(self) -> bool:
        """Whether the row declared a tag inside the schema's vocabulary."""
        return self.raw_tag in VALID_TAG


def _normalise_priority(cell: str) -> str:
    """Reduce a priority cell to `M`, `S` or `C`, or empty when it does not reduce.

    The corpus mostly writes a bare letter but sometimes qualifies it
    ("C (나중 연동)") or leaves an em dash. A qualified letter is still that
    priority; an em dash is an absent declaration and must not silently become
    a default.

    Args:
        cell: Priority cell text.

    Returns:
        (str) Normalised priority, or empty string when the cell declares none.
    """
    stripped = cell.strip()
    for value in VALID_PRIORITY:
        if stripped == value or stripped.startswith(f"{value} "):
            return value
    return ""


def _normalise_tag(cell: str) -> tuple[str, str]:
    """Extract a status marker from a remarks cell and normalise it.

    Args:
        cell: Remarks cell text, typically holding a bracketed marker.

    Returns:
        (str) Two values: the normalised tag, and the marker as written.
    """
    marker = _TAG_MARKER.search(cell)
    raw = marker.group(1) if marker else ""
    return (raw if raw in VALID_TAG else TAG_FALLBACK), raw


def _is_requirement_table(header: tuple[str, ...]) -> bool:
    """Decide whether a table declares requirements.

    Requires an `ID` column plus evidence that rows are requirements rather
    than open issues: either a priority column or a requirement-text column.
    Without this guard the open-issue tables in doc 16 (`| ID | 확정 | 근거 |`)
    are read as declarations.
    """
    plain = [plain_text(cell) for cell in header]
    if not plain or plain[0] != "ID":
        return False
    return any(cell.startswith("요구사항") or cell == "우선" for cell in plain)


def parse_spec(path: Path) -> list[Requirement]:
    """Extract every requirement one specification document declares.

    Args:
        path: Specification Markdown file.

    Returns:
        (list) Requirements in document order. Ids are matched *within* the id
        cell rather than against the whole cell, because declaration cells
        carry emphasis and status markers (`| **NFR-PRF-055** 🆕 |`).
    """
    doc_number = _DOC_NUMBER.match(path.name)
    if not doc_number:
        return []

    requirements: list[Requirement] = []
    for section in read_sections(path):
        section_number = _SECTION_NUMBER.match(section.title)
        section_label = section_number.group(1) if section_number else section.title

        for table in section.tables:
            if not _is_requirement_table(table.header):
                continue
            priority_column = table.column_index("우선")
            text_column = table.column_index("요구사항", "연동면 계약")
            remarks_column = table.column_index("비고")

            for offset, row in enumerate(table.rows):
                found = REQ_ID.search(plain_text(row[0]))
                if not found:
                    continue
                raw_priority = (
                    plain_text(row[priority_column]) if priority_column is not None else ""
                )
                tag, raw_tag = _normalise_tag(
                    plain_text(row[remarks_column]) if remarks_column is not None else ""
                )
                requirements.append(
                    Requirement(
                        req_id=found.group(0),
                        doc=doc_number.group(1),
                        section=section_label,
                        priority=_normalise_priority(raw_priority),
                        raw_priority=raw_priority,
                        tag=tag,
                        raw_tag=raw_tag,
                        text=plain_text(row[text_column]) if text_column is not None else "",
                        source=path,
                        source_line=table.header_line + 2 + offset,
                    )
                )
    return requirements


def parse_all(spec_dir: Path) -> list[Requirement]:
    """Extract every requirement the specification corpus declares.

    A requirement declared in more than one document keeps its first
    declaration; the duplicate is reported by `registry/checks/ci_01.py`
    rather than resolved here, because picking a winner is a normalisation
    decision and normalisation is Wave -1's, not the ingester's (`00` §1.2).

    Args:
        spec_dir: Directory holding the specification documents.

    Returns:
        (list) Requirements sorted by id.
    """
    seen: dict[str, Requirement] = {}
    for path in sorted(spec_dir.glob("*.md")):
        for requirement in parse_spec(path):
            seen.setdefault(requirement.req_id, requirement)
    return sorted(seen.values(), key=lambda requirement: requirement.req_id)


def find_duplicates(spec_dir: Path) -> dict[str, list[Requirement]]:
    """Return requirement ids declared more than once, with every declaration.

    Args:
        spec_dir: Directory holding the specification documents.

    Returns:
        (dict) Requirement id to its declarations, only for ids declared twice
        or more.
    """
    declarations: dict[str, list[Requirement]] = {}
    for path in sorted(spec_dir.glob("*.md")):
        for requirement in parse_spec(path):
            declarations.setdefault(requirement.req_id, []).append(requirement)
    return {req_id: found for req_id, found in declarations.items() if len(found) > 1}
