"""The closed contract namespace, read from the document that issues it.

`01` §6.2 is the sole issuing authority for contract ids (`06` §4.1 is an
explicit copy of it). This module parses that table rather than restating it,
because a literal copy here would be the second source of truth that `CI-03c`
exists to prevent: the copy would keep passing its own checks while the
canonical table drifted underneath it.

Anything outside the 13 names is an artifact, not a contract (`06` §4.1b), and
registering one is rejected rather than accommodated.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from registry.contracts.violations import SEVERITY_BLOCKING, ContractViolationError, Violation
from registry.ingest.catalog import CONTRACT_ID, WP_ID
from registry.ingest.markdown import plain_text, read_sections

CONTRACT_COUNT = 13
CANONICAL_DOC = Path("docs/plan/01-의존성-DAG-및-병렬화.md")
CANONICAL_SECTION_PREFIX = "6.2"

# `@v<n>` is the freeze generation and has no digits beneath it (`01` §6.2), so
# semver (`CTR-ACT@1.2.0`), a dotted generation (`CTR-ACT@v1.2`) and the range
# operators `CI-08` bans (`^`, `~`, `latest`, `*`) all have to fail. The anchors
# carry that: without them `CTR-ACT@1.2.0` matches at `@v`-less offset zero for
# nothing, but `CTR-ACT@v1.2` would match its own `CTR-ACT@v1` prefix and be
# accepted as a legal id for a different contract than the text names.
CONTRACT_ID_RE = re.compile(r"^CTR-(?P<name>[A-Z]+)@v(?P<version>[1-9][0-9]*)$")

_OWNER_COLUMN = "소유 WP"


@dataclass(frozen=True)
class ContractRef:
    """A parsed contract id: a namespace member plus its freeze generation.

    Attributes:
        name: Bare contract name without the `CTR-` prefix, e.g. `ACT`.
        version: Freeze generation `n` from `@v<n>`, always >= 1.
    """

    name: str
    version: int

    def __str__(self) -> str:
        """Render the canonical id text.

        Returns:
            str: The id in `CTR-<NAME>@v<n>` form.
        """
        return f"CTR-{self.name}@v{self.version}"

    def at_version(self, version: int) -> ContractRef:
        """Return the same contract at another freeze generation.

        Args:
            version: Target freeze generation.

        Returns:
            ContractRef: Reference to `CTR-<NAME>@v<version>`.
        """
        return ContractRef(name=self.name, version=version)


@dataclass(frozen=True)
class ContractDefinition:
    """One row of the canonical contract table.

    Attributes:
        ref: Contract reference at the generation the table declares.
        owner_wp: Work package that owns the contract and performs its freeze.
        source_line: 1-indexed line of the declaring row, for provenance.
    """

    ref: ContractRef
    owner_wp: str
    source_line: int


def parse_contract_id(contract_id: str) -> ContractRef:
    """Parse a contract id, rejecting every notation but `CTR-<NAME>@v<n>`.

    Args:
        contract_id: Candidate id text.

    Returns:
        ContractRef: The parsed reference.

    Raises:
        ContractViolationError: If the text is not a single-namespace contract id.
    """
    match = CONTRACT_ID_RE.match(contract_id)
    if match is None:
        raise ContractViolationError(
            Violation(
                rule="CI-08",
                severity=SEVERITY_BLOCKING,
                location=contract_id,
                expected="contract id of the form CTR-<NAME>@v<n>",
                actual=f"{contract_id!r} (semver, range operators and `latest` are not ids)",
            )
        )
    return ContractRef(name=match.group("name"), version=int(match.group("version")))


def load_catalog(repo_root: Path) -> dict[str, ContractDefinition]:
    """Read the 13 canonical contracts out of `01` §6.2.

    Args:
        repo_root: Repository root the planning documents live under.

    Returns:
        dict[str, ContractDefinition]: Definitions keyed by bare contract name.

    Raises:
        ContractViolationError: If the canonical table is missing, unparseable, or
            no longer declares exactly `CONTRACT_COUNT` contracts with one
            owner each.
    """
    doc = repo_root / CANONICAL_DOC
    sections = [
        section
        for section in read_sections(doc)
        if section.title.startswith(CANONICAL_SECTION_PREFIX)
    ]
    tables = [table for section in sections for table in section.tables]
    if len(tables) != 1:
        raise ContractViolationError(
            Violation(
                rule="CI-03c",
                severity=SEVERITY_BLOCKING,
                location=f"{CANONICAL_DOC}#{CANONICAL_SECTION_PREFIX}",
                expected="exactly one contract registry table",
                actual=f"{len(tables)} tables under the §6.2 heading",
            )
        )
    table = tables[0]
    owner_column = table.exact_column_index(_OWNER_COLUMN)
    if owner_column is None:
        raise ContractViolationError(
            Violation(
                rule="CI-03c",
                severity=SEVERITY_BLOCKING,
                location=f"{CANONICAL_DOC}#{CANONICAL_SECTION_PREFIX}",
                expected=f"a {_OWNER_COLUMN!r} column",
                actual=f"columns {[plain_text(cell) for cell in table.header]}",
            )
        )

    definitions: dict[str, ContractDefinition] = {}
    for offset, row in enumerate(table.rows):
        ids = CONTRACT_ID.findall(plain_text(row[0]))
        if len(ids) != 1:
            continue
        owners = WP_ID.findall(plain_text(row[owner_column]))
        line = table.header_line + 2 + offset
        if len(owners) != 1:
            raise ContractViolationError(
                Violation(
                    rule="CI-03",
                    severity=SEVERITY_BLOCKING,
                    location=f"{CANONICAL_DOC}:{line} {ids[0]}",
                    expected="exactly one owning work package",
                    actual=f"{owners}",
                )
            )
        ref = parse_contract_id(ids[0])
        definitions[ref.name] = ContractDefinition(ref=ref, owner_wp=owners[0], source_line=line)

    if len(definitions) != CONTRACT_COUNT:
        raise ContractViolationError(
            Violation(
                rule="CI-03c",
                severity=SEVERITY_BLOCKING,
                location=f"{CANONICAL_DOC}#{CANONICAL_SECTION_PREFIX}",
                expected=f"{CONTRACT_COUNT} contracts",
                actual=f"{len(definitions)}: {sorted(definitions)}",
            )
        )
    return definitions


def require_in_namespace(ref: ContractRef, catalog: dict[str, ContractDefinition]) -> None:
    """Reject a contract id whose name is outside the closed namespace.

    Args:
        ref: Parsed contract reference.
        catalog: Canonical definitions keyed by bare name.

    Raises:
        ContractViolationError: If the name is not one of the 13. Such a thing is an
            artifact and is linked through `artifact[]`/`downstream[]` instead
            (`06` §4.1b).
    """
    if ref.name in catalog:
        return
    raise ContractViolationError(
        Violation(
            rule="CI-03c",
            severity=SEVERITY_BLOCKING,
            location=str(ref),
            expected=f"one of the {CONTRACT_COUNT} contracts in {CANONICAL_DOC}#6.2",
            actual=f"CTR-{ref.name} is outside the namespace — it is an artifact, not a contract",
        )
    )
