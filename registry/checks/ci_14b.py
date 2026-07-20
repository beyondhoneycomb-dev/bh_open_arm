"""CI-14b — shape assignment against canon: the catalogue assigns, others cite.

`00` §9.2a splits three ways. `02a`–`02d` own *assignment*, `05` owns the
*vocabulary* only, and `01` merely *cites*. When they disagree the catalogue wins
and `01` is what gets fixed. This rule is the machine form of that comparison, and
it exists because during the period when the split was not written down, `01` and
the catalogues had drifted apart on 14 of 39 packages.

Three comparisons, per `06` §5: the registry's shape sequence against the
catalogue's shape cell, `01`'s cited shape against the catalogue when `01` states
one, and every package holding an actual `SHAPE-*` token in its catalogue cell —
prose description with no token means no assignment was made at all.

Shape sequences are compared after collapsing consecutive repeats. A catalogue
cell carries one token per distinct shape; `05` §1.1 delegates stage *count* to
`phases[]`, so the catalogue has no way to write "two consecutive stages of the
same shape" and demanding it would make the catalogue encode what it does not own.
"""

from __future__ import annotations

import re

from registry.checks.corpus import Corpus
from registry.checks.model import RuleResult, fail
from registry.checks.wp import collapse_repeats, shape_sequence
from registry.ingest.catalog import SHAPE_TOKEN, WP_ID, CatalogEntry
from registry.ingest.markdown import all_tables, plain_text, split_row

RULE_ID = "CI-14b"
TITLE = "shape assignment against canon"

DAG_DOC = "01-의존성-DAG-및-병렬화.md"

_PARENTHETICAL = re.compile(r"\([^()]*\)")


def catalog_shapes(entry: CatalogEntry) -> tuple[str, ...]:
    """Read the shape tokens a catalogue row assigns, excluding its own gloss.

    A shape cell may carry a parenthetical explaining the stage split — for
    example `SHAPE-CF → SHAPE-IM(6) (phase1 … = SHAPE-CF / phase2 … = SHAPE-IM)`.
    The gloss repeats the tokens, so counting every token in the cell reads a
    two-stage assignment as four stages. The assignment is the token sequence
    outside the parentheses; the gloss describes it and is not itself an
    assignment, the same distinction CI-10 and CI-11b draw between a value and
    the prose about it.

    Args:
        entry: Catalogue row for one work package.

    Returns:
        (tuple[str, ...]) Assigned shape tokens, in order.
    """
    line = entry.source.read_text(encoding="utf-8").splitlines()[entry.source_line - 1]
    cells = [plain_text(cell) for cell in split_row(line)]
    carrying = [cell for cell in cells if SHAPE_TOKEN.search(cell)]
    if not carrying:
        return tuple(entry.workflows)
    return tuple(SHAPE_TOKEN.findall(_PARENTHETICAL.sub(" ", carrying[-1])))


def cited_shapes(corpus: Corpus) -> dict[str, tuple[str, ...]]:
    """Read the shapes `01` cites for each work package.

    Only table cells are read. `06` §5 marks prose that *explains* a shape as an
    explicit exception, so a sentence naming a shape is not a citation.

    Args:
        corpus: The corpus under test.

    Returns:
        (dict[str, tuple[str, ...]]) `WP-*` to the shape tokens `01` cites.
    """
    path = corpus.plan_dir / DAG_DOC
    if not path.is_file():
        return {}
    cited: dict[str, tuple[str, ...]] = {}
    for table in all_tables(path):
        wp_column = table.exact_column_index("WP")
        shape_column = table.column_index("형상")
        if wp_column is None or shape_column is None:
            continue
        for row in table.rows:
            if wp_column >= len(row) or shape_column >= len(row):
                continue
            packages = WP_ID.findall(plain_text(row[wp_column]))
            tokens = tuple(SHAPE_TOKEN.findall(plain_text(row[shape_column])))
            if len(packages) == 1 and tokens:
                cited[packages[0]] = tokens
    return cited


def run(corpus: Corpus) -> RuleResult:
    """Report shape assignments that disagree with the catalogue.

    Args:
        corpus: The corpus under test.

    Returns:
        (RuleResult) One finding per mismatch or missing assignment.
    """
    citations = cited_shapes(corpus)
    findings = []
    sites = 0

    for wp_id, records in sorted(corpus.by_wp.items()):
        sites += 1
        catalog_entry = corpus.catalog.get(wp_id)
        if catalog_entry is None:
            findings.append(
                fail(
                    rule_id=RULE_ID,
                    req_or_wp=wp_id,
                    path=corpus.rel(corpus.registry_path),
                    reason="registry registers a work package that no catalogue defines",
                    expected=f"{wp_id} defined in 02a-02d",
                    actual="no catalogue row",
                )
            )
            continue

        assigned = collapse_repeats(catalog_shapes(catalog_entry))
        location = f"{corpus.rel(catalog_entry.source)}:{catalog_entry.source_line}"

        if not assigned:
            findings.append(
                fail(
                    rule_id=RULE_ID,
                    req_or_wp=wp_id,
                    path=location,
                    reason=(
                        "catalogue row holds no SHAPE-* token; prose description without a "
                        "token means no shape was assigned"
                    ),
                    expected="exactly one SHAPE-* token per stage in the shape cell",
                    actual="(no token)",
                )
            )
            continue

        registry_shapes = collapse_repeats(shape_sequence(records[0]))
        if registry_shapes != assigned:
            findings.append(
                fail(
                    rule_id=RULE_ID,
                    req_or_wp=wp_id,
                    path=corpus.rel(corpus.registry_path),
                    reason="registry shape sequence disagrees with the catalogue, which is canon",
                    expected=" -> ".join(assigned),
                    actual=" -> ".join(registry_shapes) or "(no shape declared)",
                )
            )

        citation = collapse_repeats(citations.get(wp_id, ()))
        if citation and citation != assigned:
            findings.append(
                fail(
                    rule_id=RULE_ID,
                    req_or_wp=wp_id,
                    path=corpus.rel(corpus.plan_dir / DAG_DOC),
                    reason=(
                        "01 cites a shape that disagrees with the catalogue; fix 01, not "
                        "the catalogue"
                    ),
                    expected=" -> ".join(assigned),
                    actual=" -> ".join(citation),
                )
            )

    return RuleResult(rule_id=RULE_ID, findings=tuple(findings), sites=sites, vacuous=not sites)
