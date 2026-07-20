"""CI-04c — `CG-*` derivation consistency: the catalogue issues acceptance ids.

`06` §2.4a and `00` §8.0 derive `CG-<band>-<nn><letter>` from the *letter*-th
acceptance item of `WP-<band>-<nn>`. The catalogue is canon: `02c`/`02d` write
some `CG-*` ids explicitly and those must equal the derived value, while `02a`/`02b`
write none and the derived value simply is the id. Either way the registry may not
mint an acceptance id of its own — the catalogue's acceptance items are the source.

A letter beyond the item count is the common failure: it names an acceptance item
that does not exist, so nothing can ever satisfy it.
"""

from __future__ import annotations

from registry.checks.corpus import Corpus
from registry.checks.model import RuleResult, fail
from registry.checks.wp import acceptance_count, derive_cg_id, parse_cg_id

RULE_ID = "CI-04c"
TITLE = "CG-* derivation consistency"


def run(corpus: Corpus) -> RuleResult:
    """Report acceptance ids that do not derive from a catalogue acceptance item.

    Args:
        corpus: The corpus under test.

    Returns:
        (RuleResult) One finding per malformed or underived acceptance id.
    """
    findings = []
    sites = 0
    reported: set[tuple[str, str]] = set()

    for wp_id, records in sorted(corpus.by_wp.items()):
        catalog_entry = corpus.catalog.get(wp_id)
        items = acceptance_count(catalog_entry.acceptance_text) if catalog_entry else 0

        gates = {g for record in records for g in record.get("gate", []) or []}
        for gate in sorted(str(g) for g in gates):
            if not gate.startswith("CG-"):
                continue
            sites += 1
            key = (wp_id, gate)
            if key in reported:
                continue

            parsed = parse_cg_id(gate)
            if parsed is None:
                reported.add(key)
                findings.append(
                    fail(
                        rule_id=RULE_ID,
                        req_or_wp=f"{wp_id}/{gate}",
                        path=corpus.rel(corpus.registry_path),
                        reason="acceptance id does not parse as CG-<band>-<nn><letter>",
                        expected=f"{derive_cg_id(wp_id, 1)} shape",
                        actual=gate,
                    )
                )
                continue

            derived_wp, ordinal = parsed
            if derived_wp != wp_id:
                reported.add(key)
                findings.append(
                    fail(
                        rule_id=RULE_ID,
                        req_or_wp=f"{wp_id}/{gate}",
                        path=corpus.rel(corpus.registry_path),
                        reason=(
                            "acceptance id derives from a different work package than the "
                            "record's wp"
                        ),
                        expected=f"an id deriving from {wp_id}",
                        actual=f"derives from {derived_wp}",
                    )
                )
                continue

            if catalog_entry is None:
                reported.add(key)
                findings.append(
                    fail(
                        rule_id=RULE_ID,
                        req_or_wp=f"{wp_id}/{gate}",
                        path=corpus.rel(corpus.registry_path),
                        reason="acceptance id references a work package absent from 02a-02d",
                        expected=f"{wp_id} defined in a catalogue",
                        actual="no catalogue row",
                    )
                )
                continue

            if ordinal > items:
                reported.add(key)
                findings.append(
                    fail(
                        rule_id=RULE_ID,
                        req_or_wp=f"{wp_id}/{gate}",
                        path=f"{corpus.rel(catalog_entry.source)}:{catalog_entry.source_line}",
                        reason=(
                            "acceptance id's letter is beyond the catalogue's acceptance item "
                            "count, so it names an item that does not exist"
                        ),
                        expected=f"letter ordinal <= {items} acceptance item(s)",
                        actual=f"ordinal {ordinal}",
                    )
                )

    return RuleResult(rule_id=RULE_ID, findings=tuple(findings), sites=sites, vacuous=not sites)
