"""Semantic validation of the normalization ledger against the live corpus.

Schema validity (`loader.schema_errors`) proves the ledger has the right shape.
This module proves the ledger tells the truth about the corpus it rules over:

* every winning id resolves to exactly one definition — an `FR-*`/`NFR-*` declared
  in a `docs/spec` table, a `D-n`/`M-n` defined in `docs/spec/16`, a `PG-*`
  declared in the `docs/plan/03` gate table;
* every discarded quote is present, character-exact, at its `file:section` — with
  Markdown emphasis markers and runs of whitespace normalized the same way every
  CI checker normalizes them (`registry.ingest.markdown.plain_text`), because
  `**` is presentation and not content, and a safety quote is never paraphrased;
* every enforcement names a check that resolves — an existing CI executable
  (`registry/checks/ci_*.py`) or the issued work package that implements it.

A ledger that passes schema but fails here would be green while pointing at ids
and quotes that do not exist: the exact "green but catching nothing" failure the
ledger exists to prevent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from registry.ingest.build import read_contract_producers
from registry.ingest.catalog import parse_all as parse_catalogs
from registry.ingest.markdown import all_tables, plain_text, read_sections
from registry.ingest.spec import parse_all as parse_spec

GATE_DOC = "03-측정-게이트.md"
DOC16_PREFIX = "16"
GATE_ID_COLUMN = "ID"
GATE_CELL_STRIP = "🔴 "

_FR_NFR = re.compile(r"^(?:FR|NFR)-[A-Z]{2,4}-\d{3}$")
_DM = re.compile(r"^[DM]-\d+$")
_PG = re.compile(r"^PG-[A-Z0-9]+-\d{3}[ab]?$")
_CI_CHECK = re.compile(r"^CI-(\d+[a-z]?)$")
_WP_CHECK = re.compile(r"^WP-[A-Z0-9-]+$")
_CTR_CONTRACT = re.compile(r"^CTR-[A-Z]+@v\d+$")
_GATE_REGISTRY_CONTRACT = re.compile(r"^gate-registry:(WP-[A-Z0-9-]+)$")
_SECTION_NUMBER = re.compile(r"^(\d+(?:\.\d+)*[a-z]?)(?:\s|$)")


@dataclass(frozen=True)
class Violation:
    """One ledger claim the corpus does not support.

    Attributes:
        norm_id: The ledger row or note the violation belongs to.
        kind: Which class of claim failed (winner, quote, enforcement, contract).
        detail: What was asserted and what the corpus actually holds.
    """

    norm_id: str
    kind: str
    detail: str

    def as_line(self) -> str:
        """Render the violation as one report line.

        Returns:
            (str) Single-line human-readable form.
        """
        return f"{self.norm_id} [{self.kind}] {self.detail}"


@dataclass
class Corpus:
    """The corpus facts the ledger is validated against, resolved once.

    Attributes:
        root: Repository root.
        spec_dir: Directory holding the specification documents.
        plan_dir: Directory holding the planning documents.
        spec_requirements: Declared `FR-*`/`NFR-*` ids.
        gate_roster: `PG-*` ids declared in the `03` gate table.
        issued_wps: Work-package ids the catalogs issue.
        contract_producers: Frozen contract id to its producing package.
    """

    root: Path
    spec_dir: Path
    plan_dir: Path
    spec_requirements: frozenset[str]
    gate_roster: frozenset[str]
    issued_wps: frozenset[str]
    contract_producers: dict[str, str]

    @classmethod
    def load(cls, root: Path) -> Corpus:
        """Resolve every corpus fact the validator needs from a repository root.

        Args:
            root: Repository root.

        Returns:
            (Corpus) The resolved corpus facts.
        """
        spec_dir = root / "docs" / "spec"
        plan_dir = root / "docs" / "plan"
        return cls(
            root=root,
            spec_dir=spec_dir,
            plan_dir=plan_dir,
            spec_requirements=frozenset(req.req_id for req in parse_spec(spec_dir)),
            gate_roster=_gate_roster(plan_dir),
            issued_wps=frozenset(entry.wp_id for entry in parse_catalogs(plan_dir)),
            contract_producers=read_contract_producers(plan_dir),
        )

    def spec_file(self, number: str) -> Path | None:
        """Return the specification document with a given two-digit number.

        Args:
            number: Two-digit document number, e.g. `13`.

        Returns:
            (Path | None) The document path, or None when no document matches.
        """
        matches = sorted(self.spec_dir.glob(f"{number}-*.md"))
        return matches[0] if matches else None

    def dm_definition_count(self, dm_id: str) -> int:
        """Count the definition rows for a `D-n`/`M-n` id in `docs/spec/16`.

        A definition is a table row that opens with the bold id (`| **M-20** |`),
        which distinguishes it from the many prose citations of the same id.

        Args:
            dm_id: A `D-n` or `M-n` id.

        Returns:
            (int) Number of definition rows.
        """
        path = self.spec_file(DOC16_PREFIX)
        if path is None:
            return 0
        pattern = re.compile(rf"^\|\s*\*\*{re.escape(dm_id)}\*\*\s*\|", re.MULTILINE)
        return len(pattern.findall(path.read_text(encoding="utf-8")))


def _gate_roster(plan_dir: Path) -> frozenset[str]:
    """Read the `PG-*` ids the `03` gate table declares in its ID column.

    Args:
        plan_dir: Directory holding the planning documents.

    Returns:
        (frozenset[str]) Declared gate ids.
    """
    path = plan_dir / GATE_DOC
    if not path.is_file():
        return frozenset()
    roster: set[str] = set()
    for table in all_tables(path):
        if not table.header or plain_text(table.header[0]) != GATE_ID_COLUMN:
            continue
        for row in table.rows:
            value = plain_text(row[0]).lstrip(GATE_CELL_STRIP).strip()
            if value:
                roster.add(value)
    return frozenset(roster)


def section_body(path: Path, section: str) -> str | None:
    """Return the normalized text of a numbered section.

    The span runs from the section heading to the next heading of the same or a
    higher level, so a section owns its deeper subsections. The text is passed
    through `plain_text`, so a quote matches regardless of emphasis markup or
    whitespace runs but not regardless of its words.

    Args:
        path: Document to read.
        section: Numbered section, e.g. `4.2`.

    Returns:
        (str | None) Normalized section text, or None when the section is absent.
    """
    sections = read_sections(path)
    matches = [
        (index, sec) for index, sec in enumerate(sections) if _matches_section(sec.title, section)
    ]
    if not matches:
        return None
    index, target = matches[-1]
    lines = path.read_text(encoding="utf-8").splitlines()
    end = len(lines)
    for following in sections[index + 1 :]:
        if following.level <= target.level:
            end = following.line - 1
            break
    return plain_text("\n".join(lines[target.line - 1 : end]))


def _matches_section(title: str, section: str) -> bool:
    """Return whether a heading's leading number equals a section number.

    Args:
        title: Heading text with the `#` markers already stripped.
        section: The section number to match.

    Returns:
        (bool) True when the heading's number token equals `section`.
    """
    match = _SECTION_NUMBER.match(title.strip())
    return match is not None and match.group(1) == section


def _id_resolves(corpus: Corpus, canonical_id: str) -> bool:
    """Return whether a canonical id resolves to exactly one definition.

    Args:
        corpus: The corpus facts.
        canonical_id: An `FR-*`/`NFR-*`, `D-n`/`M-n`, or `PG-*` id.

    Returns:
        (bool) True when the id has a single corpus definition.
    """
    if _FR_NFR.match(canonical_id):
        return canonical_id in corpus.spec_requirements
    if _DM.match(canonical_id):
        return corpus.dm_definition_count(canonical_id) == 1
    if _PG.match(canonical_id):
        return canonical_id in corpus.gate_roster
    return False


def _check_resolves(corpus: Corpus, check: str) -> bool:
    """Return whether an enforcement check reference resolves to something real.

    Args:
        corpus: The corpus facts.
        check: A `CI-*` rule id or a `WP-*` id.

    Returns:
        (bool) True for an existing CI executable or an issued work package.
    """
    ci_match = _CI_CHECK.match(check)
    if ci_match:
        module = corpus.root / "registry" / "checks" / f"ci_{ci_match.group(1).lower()}.py"
        return module.is_file()
    if _WP_CHECK.match(check):
        return check in corpus.issued_wps
    return False


def _validate_row(corpus: Corpus, row: dict[str, Any]) -> list[Violation]:
    """Validate one ledger row against the corpus.

    Args:
        corpus: The corpus facts.
        row: A schema-valid ledger row.

    Returns:
        (list[Violation]) Violations found in this row.
    """
    norm_id = str(row.get("norm_id", "?"))
    violations: list[Violation] = []

    for winner in row.get("winners", []):
        if not _id_resolves(corpus, winner):
            violations.append(
                Violation(norm_id, "winner", f"{winner} has no single corpus definition")
            )

    for item in row.get("discarded", []):
        number, section, quote = item.get("file"), item.get("section"), item.get("quote", "")
        path = corpus.spec_file(str(number))
        if path is None:
            violations.append(Violation(norm_id, "quote", f"spec file {number} not found"))
        else:
            body = section_body(path, str(section))
            if body is None:
                violations.append(
                    Violation(norm_id, "quote", f"section {number}#{section} not found")
                )
            elif quote not in body:
                violations.append(
                    Violation(
                        norm_id,
                        "quote",
                        f"quote absent at {number}#{section}: {quote[:60]!r}",
                    )
                )
        req = item.get("req")
        if req is not None and not _id_resolves(corpus, str(req)):
            violations.append(
                Violation(norm_id, "discarded-req", f"{req} has no single corpus definition")
            )

    violations.extend(_validate_contract(corpus, norm_id, str(row.get("contract", ""))))

    for entry in row.get("enforcement", []):
        check = str(entry.get("check", ""))
        if not _check_resolves(corpus, check):
            violations.append(
                Violation(norm_id, "enforcement", f"check {check!r} resolves to no executable")
            )

    return violations


def _validate_contract(corpus: Corpus, norm_id: str, contract: str) -> list[Violation]:
    """Validate a row's owning-contract reference.

    Args:
        corpus: The corpus facts.
        norm_id: The row the contract belongs to.
        contract: The `contract` field value.

    Returns:
        (list[Violation]) A single violation when the reference dangles, else none.
    """
    if _CTR_CONTRACT.match(contract):
        if contract not in corpus.contract_producers:
            return [Violation(norm_id, "contract", f"{contract} has no declared producer")]
        return []
    registry_match = _GATE_REGISTRY_CONTRACT.match(contract)
    if registry_match:
        owner = registry_match.group(1)
        if owner not in corpus.issued_wps:
            return [Violation(norm_id, "contract", f"gate-registry owner {owner} is not issued")]
        return []
    detail = f"{contract!r} is neither a contract nor a gate registry"
    return [Violation(norm_id, "contract", detail)]


def validate(corpus: Corpus, document: dict[str, Any]) -> list[Violation]:
    """Validate a schema-valid ledger document against the corpus.

    Args:
        corpus: The corpus facts.
        document: A ledger document that has already passed schema validation.

    Returns:
        (list[Violation]) Every unsupported claim, in row order.
    """
    violations: list[Violation] = []
    for row in document.get("rows", []):
        violations.extend(_validate_row(corpus, row))
    return violations
