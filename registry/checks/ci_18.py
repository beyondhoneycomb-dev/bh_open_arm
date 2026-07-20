"""CI-18 — bootstrap precedence: nothing starts before the BOOT band lands.

Build range is `CI-01`..`CI-18`; judge range is `CI-01`..`CI-17`. The two numbers
differ on purpose and `02a` §−2.3 warns against "correcting" them to match.

This rule exists because `06` §5 contains it, and a rule that exists without an
executable is exactly the "unenforced declaration" that `00` §3.5 set out to
abolish — with the added embarrassment that it would be the rule guarding
bootstrap precedence which went unenforced.

It is excluded from BOOT's own acceptance for two reasons. Its predicate cites the
band acceptance gate's two conditions (all 177 registered, `CI-01`..`CI-17` green),
so folding it into that gate makes the gate reference itself. And it only ever
looks at packages *outside* the BOOT band, so at the moment BOOT lands it is
vacuously true and guarantees nothing. Its meaning begins after landing, which is
what `06` §5 means by "the rule that guards the rest once bootstrap is down".
"""

from __future__ import annotations

import json
from typing import Any

from registry.checks.corpus import Corpus
from registry.checks.model import RuleResult, fail

RULE_ID = "CI-18"
TITLE = "bootstrap precedence"

BOOT_BAND = "BOOT"
STATE_STORE = "registry/state/workflow_state.json"

# `05` state vocabulary: these mean the package has been started.
STARTED_STATES = frozenset({"활성", "active", "started", "통합됨", "integrated"})

EXPECTED_WORK_PACKAGES = 177


def _band(wp_id: str) -> str:
    """Extract the band token from a work-package id.

    Args:
        wp_id: Work-package id.

    Returns:
        (str) Band token, or empty when the id has no band.
    """
    parts = wp_id.split("-")
    return parts[1] if len(parts) > 2 else ""


def _started(corpus: Corpus) -> dict[str, str]:
    """Read which work packages the state store marks as started.

    Args:
        corpus: The corpus under test.

    Returns:
        (dict[str, str]) `WP-*` to its state, for started packages only.
    """
    path = corpus.root / STATE_STORE
    if not path.is_file():
        return {}
    loaded: Any = json.loads(path.read_text(encoding="utf-8"))
    states = loaded.get("states", loaded) if isinstance(loaded, dict) else {}
    if not isinstance(states, dict):
        return {}
    return {
        str(wp_id): str(state) for wp_id, state in states.items() if str(state) in STARTED_STATES
    }


def run(corpus: Corpus, judge_findings: int | None = None) -> RuleResult:
    """Report packages started while the band acceptance gate is unmet.

    Args:
        corpus: The corpus under test.
        judge_findings: Total findings from `CI-01`..`CI-17`, or None when unknown.

    Returns:
        (RuleResult) One finding per package started too early.
    """
    started = _started(corpus)
    outside = {wp: state for wp, state in started.items() if _band(wp) != BOOT_BAND}

    registered = len(corpus.by_wp)
    all_registered = registered >= EXPECTED_WORK_PACKAGES
    judged_green = judge_findings == 0
    gate_met = all_registered and judged_green

    unmet = []
    if not all_registered:
        unmet.append(f"only {registered} of {EXPECTED_WORK_PACKAGES} work packages registered")
    if not judged_green:
        detail = "unknown" if judge_findings is None else str(judge_findings)
        unmet.append(f"CI-01..CI-17 not green (findings: {detail})")

    findings = []
    if not gate_met:
        for wp_id, state in sorted(outside.items()):
            findings.append(
                fail(
                    rule_id=RULE_ID,
                    req_or_wp=wp_id,
                    path=STATE_STORE,
                    reason=(
                        "work package outside the BOOT band is marked started while the band "
                        "acceptance gate is unmet; no package may start, Wave -1 included"
                    ),
                    expected="not started until 177 registered and CI-01..CI-17 green",
                    actual=f"state={state}; gate unmet because {'; '.join(unmet)}",
                )
            )

    return RuleResult(
        rule_id=RULE_ID,
        findings=tuple(findings),
        sites=len(outside),
        vacuous=not outside,
        notes=(
            (
                "no work package outside the BOOT band is marked started, so this rule is "
                "vacuously true — as 06 §5 expects at bootstrap landing time.",
            )
            if not outside
            else ()
        ),
    )
