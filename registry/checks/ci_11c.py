"""CI-11c — provisional consumption must be marked: `a` is not final, `b` is.

`PG-RT-001a` measures the control loop under a synthetic GIL load and is
provisional; `PG-RT-001b` measures it against real cameras and real writes and is
final. Anything derived from `a` alone — `ART-F-MAX-PYTHON` and everything
downstream of it — must declare `PG-RT-001b:PASS` in `stale_on[]`, so that
confirming `b` forces re-derivation. Without that trigger, a number computed from
a synthetic load survives as though it were the final figure.

Downstream is followed transitively, because the whole hazard is a provisional
number propagating: stopping at the first hop would let the second hop keep it.
"""

from __future__ import annotations

from collections import deque

from registry.checks.corpus import Corpus
from registry.checks.model import RuleResult, fail

RULE_ID = "CI-11c"
TITLE = "provisional consumption marked"

PROVISIONAL_GATE = "PG-RT-001a"
FINAL_GATE = "PG-RT-001b"
REQUIRED_TRIGGER = f"{FINAL_GATE}:PASS"


def _downstream_closure(corpus: Corpus, seeds: set[str]) -> set[str]:
    """Follow `downstream[]` work-package edges transitively from the seeds.

    Args:
        corpus: The corpus under test.
        seeds: Work packages to start from.

    Returns:
        (set[str]) Seeds plus every work package reachable from them.
    """
    reached = set(seeds)
    queue = deque(seeds)
    while queue:
        current = queue.popleft()
        for record in corpus.by_wp.get(current, ()):
            for target in record.get("downstream", []) or []:
                target_id = str(target)
                if target_id.startswith("WP-") and target_id not in reached:
                    reached.add(target_id)
                    queue.append(target_id)
    return reached


def run(corpus: Corpus) -> RuleResult:
    """Report packages derived from the provisional gate without the final trigger.

    Args:
        corpus: The corpus under test.

    Returns:
        (RuleResult) One finding per package missing the re-derivation trigger.
    """
    seeds = {
        wp_id
        for wp_id, records in corpus.by_wp.items()
        if any(PROVISIONAL_GATE in (r.get("gate", []) or []) for r in records)
        and not any(FINAL_GATE in (r.get("gate", []) or []) for r in records)
    }
    scope = _downstream_closure(corpus, seeds)

    findings = []
    for wp_id in sorted(scope):
        records = corpus.by_wp.get(wp_id, ())
        if not records:
            continue
        triggers = {str(t) for record in records for t in record.get("stale_on", []) or []}
        if REQUIRED_TRIGGER in triggers:
            continue
        origin = "gated on the provisional measurement" if wp_id in seeds else "downstream of it"
        findings.append(
            fail(
                rule_id=RULE_ID,
                req_or_wp=wp_id,
                path=corpus.rel(corpus.registry_path),
                reason=(
                    f"package is {origin} but declares no re-derivation trigger for the final "
                    "measurement, so a synthetic-load figure can survive as final"
                ),
                expected=f"{REQUIRED_TRIGGER} in stale_on[]",
                actual=", ".join(sorted(triggers)) or "(stale_on[] is empty)",
            )
        )

    return RuleResult(
        rule_id=RULE_ID, findings=tuple(findings), sites=len(scope), vacuous=not scope
    )
