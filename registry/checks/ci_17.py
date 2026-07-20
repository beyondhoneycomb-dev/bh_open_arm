"""CI-17 — document references must exist: every citation resolves to something real.

`06` §5 gives four clauses and the note attached to them says why the rule exists:
`02-작업패키지.md` does not exist, and the canon is `02a`/`02b`/`02c`/`02d`. A
citation of a document that was never written reads as authority and carries none.

1. `docs/plan/*.md` paths cited by this registry and by `06` itself.
2. `spec_ref` of the form `<doc>#<section>` — the section must exist, including the
   plan-canon sections that `PLAN-*` records point at.
3. `spine_ref` must be a real file path plus commit, never a bare `"SPINE vN"`.
4. `SPINE §N` citations in prose must resolve through the `00` §9.0 rebinding
   table; `§A`, `§B`, `§0` and any number absent from that table fail.
"""

from __future__ import annotations

import re

import yaml

from registry.checks.corpus import Corpus
from registry.checks.model import RuleResult, fail
from registry.ingest.markdown import all_tables, plain_text, read_sections

RULE_ID = "CI-17"
TITLE = "document references exist"

REBINDING_DOC = "00-실행계획-개요.md"

SPEC_REF = re.compile(r"^(?P<doc>[0-9]{2})#(?P<section>.+)$")
SPINE_CITATION = re.compile(r"SPINE\s*§\s*(?P<token>[A-Z0-9](?:[0-9]|-[0-9A-Z]|\.[0-9])*)")
SPINE_REF_WITH_COMMIT = re.compile(r"^(?P<path>[^@]+)@(?P<commit>[0-9a-f]{7,40})$")
PLAN_DOC_PATH = re.compile(r"docs/plan/[0-9A-Za-z가-힣._-]+\.md")

REBINDING_SECTION_MARKER = "9.0"

# `N` is the rebinding table's metavariable for "any section number", not a
# citation of a section literally named N. Same shape of trap as CI-10 and
# CI-11b: the text that defines the resolution is not subject to it.
METAVARIABLE_TOKENS = frozenset({"N", "2-N"})

# A row whose target cell says the referent is absent declares its tokens
# unresolvable; listing them in the table is not the same as resolving them.
ABSENT_REFERENT_MARKER = "참조처 부재"

_FAMILY_TOKEN = re.compile(r"^(?P<family>[0-9]+)-(?P<member>[0-9]+)$")


def rebinding_tokens(corpus: Corpus) -> tuple[frozenset[str], frozenset[str]]:
    """Read what the `00` §9.0 rebinding table can and cannot resolve.

    Args:
        corpus: The corpus under test.

    Returns:
        (tuple[frozenset[str], frozenset[str]]) Resolvable tokens, then the
        families (such as `2` from a `SPINE §2-N` row) whose members resolve.
    """
    path = corpus.plan_dir / REBINDING_DOC
    if not path.is_file():
        return frozenset(), frozenset()
    resolvable: set[str] = set()
    families: set[str] = set()
    for table in all_tables(path):
        header = " ".join(plain_text(cell) for cell in table.header)
        if "SPINE" not in header:
            continue
        for row in table.rows:
            if not row:
                continue
            source = plain_text(row[0])
            target = " ".join(plain_text(cell) for cell in row[1:])
            tokens = {m.group("token") for m in SPINE_CITATION.finditer(source)}
            if ABSENT_REFERENT_MARKER in target:
                continue
            for token in tokens:
                if token in METAVARIABLE_TOKENS:
                    family = token.split("-", 1)[0]
                    if family.isdigit():
                        families.add(family)
                    continue
                resolvable.add(token)
    return frozenset(resolvable), frozenset(families)


def _resolves(token: str, resolvable: frozenset[str], families: frozenset[str]) -> bool:
    """Report whether a spine citation token resolves through the rebinding table.

    Args:
        token: Citation token such as `5` or `2-1`.
        resolvable: Tokens the table resolves directly.
        families: Families whose members the table resolves as a group.

    Returns:
        (bool) True when the citation can be resolved.
    """
    if token in resolvable:
        return True
    member = _FAMILY_TOKEN.match(token)
    return bool(member and member.group("family") in families)


def _rebinding_span(corpus: Corpus) -> tuple[int, int]:
    """Locate the line range of the `00` §9.0 rebinding section.

    The section that defines how spine citations resolve writes those citations
    as its own subject matter, so it is not a citation site.

    Args:
        corpus: The corpus under test.

    Returns:
        (tuple[int, int]) Inclusive start line and exclusive end line.
    """
    path = corpus.plan_dir / REBINDING_DOC
    if not path.is_file():
        return (0, 0)
    sections = read_sections(path)
    for index, section in enumerate(sections):
        if section.title.lstrip("#").strip().startswith(REBINDING_SECTION_MARKER):
            end = sections[index + 1].line if index + 1 < len(sections) else 1 << 30
            return (section.line, end)
    return (0, 0)


def run(corpus: Corpus) -> RuleResult:
    """Report citations that resolve to no real document, section, or commit.

    Args:
        corpus: The corpus under test.

    Returns:
        (RuleResult) One finding per dangling reference.
    """
    findings = []
    sites = 0
    plan_files = {corpus.rel(path) for path in corpus.plan_paths}

    # Serialised from the loaded registry rather than re-read from disk: the corpus
    # is the source of truth, and re-reading the file would bypass it.
    registry_text = yaml.safe_dump(corpus.registry, allow_unicode=True, sort_keys=False)
    doc06 = corpus.plan_dir / "06-추적성-레지스트리.md"
    sources = [(corpus.rel(corpus.registry_path), registry_text)]
    if doc06.is_file():
        sources.append((corpus.rel(doc06), doc06.read_text(encoding="utf-8")))

    for origin, text in sources:
        for cited in sorted(set(PLAN_DOC_PATH.findall(text))):
            sites += 1
            if cited in plan_files:
                continue
            findings.append(
                fail(
                    rule_id=RULE_ID,
                    req_or_wp="(document reference)",
                    path=origin,
                    reason="cites a planning document path that does not exist",
                    expected="an existing docs/plan/*.md file",
                    actual=cited,
                )
            )

    for record in corpus.entries:
        raw = str(record.get("spec_ref", "") or "")
        sites += 1
        match = SPEC_REF.match(raw)
        if not match:
            findings.append(
                fail(
                    rule_id=RULE_ID,
                    req_or_wp=str(record.get("req", "?")),
                    path=corpus.rel(corpus.registry_path),
                    reason="spec_ref is not of the form <document number>#<section>",
                    expected='e.g. "12#3.1"',
                    actual=raw or "(empty)",
                )
            )
            continue
        doc, section = match.group("doc"), match.group("section")
        known = corpus.spec_sections.get(doc) or corpus.plan_sections.get(doc)
        if known is None:
            findings.append(
                fail(
                    rule_id=RULE_ID,
                    req_or_wp=str(record.get("req", "?")),
                    path=corpus.rel(corpus.registry_path),
                    reason="spec_ref cites a document number with no matching document",
                    expected="a document number present in docs/spec or docs/plan",
                    actual=raw,
                )
            )
            continue
        if section not in known:
            findings.append(
                fail(
                    rule_id=RULE_ID,
                    req_or_wp=str(record.get("req", "?")),
                    path=corpus.rel(corpus.registry_path),
                    reason="spec_ref cites a section the document does not declare",
                    expected=f"a section heading numbered {section} in document {doc}",
                    actual=raw,
                )
            )

    spine_ref = str(corpus.registry.get("spine_ref", "") or "")
    sites += 1
    spine_match = SPINE_REF_WITH_COMMIT.match(spine_ref)
    if not spine_match or not (corpus.root / spine_match.group("path")).is_file():
        findings.append(
            fail(
                rule_id=RULE_ID,
                req_or_wp="(spine_ref)",
                path=corpus.rel(corpus.registry_path),
                reason=(
                    "spine_ref is not an existing file path plus commit; a bare "
                    '"SPINE vN" names nothing'
                ),
                expected="<existing path>@<commit sha>",
                actual=spine_ref or "(empty)",
            )
        )

    resolvable, families = rebinding_tokens(corpus)
    skip_start, skip_end = _rebinding_span(corpus)
    rebinding_path = corpus.plan_dir / REBINDING_DOC

    for path in corpus.plan_paths:
        in_rebinding_doc = path == rebinding_path
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if in_rebinding_doc and skip_start <= number < skip_end:
                continue
            for token in sorted({m.group("token") for m in SPINE_CITATION.finditer(line)}):
                if token in METAVARIABLE_TOKENS:
                    continue
                sites += 1
                if _resolves(token, resolvable, families):
                    continue
                findings.append(
                    fail(
                        rule_id=RULE_ID,
                        req_or_wp="(SPINE citation)",
                        path=f"{corpus.rel(path)}:{number}",
                        reason=(
                            "prose cites a SPINE section the 00 §9.0 rebinding table cannot "
                            "resolve; the table lists it as having no referent"
                        ),
                        expected=f"one of {', '.join(sorted(resolvable))}",
                        actual=f"SPINE §{token}",
                    )
                )

    return RuleResult(rule_id=RULE_ID, findings=tuple(findings), sites=sites, vacuous=not sites)
