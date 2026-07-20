"""CI-14c — cross-record consistency: package-level fields must not drift.

Records are keyed by requirement, so a package implementing several requirements
owns several records. `06` §5 splits the fields three ways and only the first
group is checked here:

* (A) package-level — `workflow`, `exec_class`, `phases`, `owns`, `gate`,
  `negative_branch`, `stale_on`, `downstream`, `contract.produces`, `targets`,
  `terminal`, `env_hash`. These belong to the package, so every record under one
  `wp` must agree. Disagreement is silent drift.
* (B) requirement-unique — `req`, `spec_ref`, `priority`, `tag`, `normalization`.
  Differing is the normal case.
* (C) may vary per requirement or artifact — `artifact`, `contract.consumes`,
  `planned`, `justification`.

`downstream[]` drift is called out specifically in `06` §5, because it shifts the
descendant set that stale propagation walks: the same package would invalidate
different successors depending on which of its records was read.
"""

from __future__ import annotations

from registry.checks.corpus import Corpus
from registry.checks.model import Finding, RuleResult, fail
from registry.checks.wp import (
    WP_IDENTICAL_CONTRACT_FIELDS,
    WP_IDENTICAL_FIELDS,
    canonical,
)

RULE_ID = "CI-14c"
TITLE = "cross-record consistency"


def run(corpus: Corpus) -> RuleResult:
    """Report package-level fields that differ between records of one package.

    Args:
        corpus: The corpus under test.

    Returns:
        (RuleResult) One finding per drifting field.
    """
    findings = []
    sites = 0

    for wp_id, records in sorted(corpus.by_wp.items()):
        if len(records) < 2:
            continue

        for name in WP_IDENTICAL_FIELDS:
            sites += 1
            variants = {canonical(record.get(name)) for record in records}
            if len(variants) < 2:
                continue
            findings.append(_drift(corpus, wp_id, name, variants, len(records)))

        for name in WP_IDENTICAL_CONTRACT_FIELDS:
            sites += 1
            variants = {
                canonical((record.get("contract", {}) or {}).get(name)) for record in records
            }
            if len(variants) < 2:
                continue
            findings.append(_drift(corpus, wp_id, f"contract.{name}", variants, len(records)))

    return RuleResult(rule_id=RULE_ID, findings=tuple(findings), sites=sites, vacuous=not sites)


def _drift(corpus: Corpus, wp_id: str, name: str, variants: set[str], record_count: int) -> Finding:
    """Build the finding for one drifting package-level field.

    Args:
        corpus: The corpus under test.
        wp_id: The work package whose records disagree.
        name: Field name that drifted.
        variants: Distinct serialised values observed.
        record_count: How many records the package has.

    Returns:
        (Finding) The drift report.
    """
    sample = sorted(variants)
    return fail(
        rule_id=RULE_ID,
        req_or_wp=wp_id,
        path=corpus.rel(corpus.registry_path),
        reason=(
            f"package-level field `{name}` differs between records of the same work package; "
            "record granularity is req, but this field belongs to the package"
        ),
        expected=f"one value across all {record_count} records",
        actual=f"{len(variants)} distinct values, e.g. {sample[0][:80]} vs {sample[1][:80]}",
    )
