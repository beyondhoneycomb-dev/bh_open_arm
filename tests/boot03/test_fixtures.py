"""Every rule must be able to fail, and must not fire on a clean corpus.

`02a` §−2.3 acceptance ② and ③. These two tests are the ones that decide whether
this package delivered checkers or decorations: a rule that cannot be made to fail
has not been shown to check anything, and a rule that fires on a clean corpus
blocks work for no reason.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from registry.checks import BUILD_RANGE, module_for
from registry.checks.fixtures.cases import (
    CASES,
    COMMIT_SCOPED_RULES,
    EXEMPTION_CASES,
    STAGE_CASES,
)

CASE_IDS = [case.rule_id for case in CASES]


def test_every_rule_has_a_fixture_pair() -> None:
    """Every executable in the roster is exercised by a fixture pair."""
    covered = {case.rule_id for case in CASES} | set(COMMIT_SCOPED_RULES)
    missing = [module.RULE_ID for module in BUILD_RANGE if module.RULE_ID not in covered]
    assert not missing, f"rules with no fixture pair: {missing}"


@pytest.mark.fixture_corpus
@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_violation_fixture_fails_the_rule(case, tmp_path: Path) -> None:
    """The violating fixture makes its rule report a violation."""
    result = module_for(case.rule_id).run(case.violating(tmp_path))
    assert result.findings, (
        f"{case.rule_id} stayed green on a corpus that violates it ({case.note}); "
        "a checker that catches nothing forges evidence that the rule is upheld"
    )
    assert all(f.rule_id == case.rule_id for f in result.findings)


@pytest.mark.fixture_corpus
@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_pass_fixture_keeps_the_rule_green(case, tmp_path: Path) -> None:
    """The passing fixture does not trip its rule."""
    result = module_for(case.rule_id).run(case.passing(tmp_path))
    assert not result.findings, (
        f"{case.rule_id} over-blocks: it fired on a compliant corpus with "
        f"{[f.reason for f in result.findings]}"
    )


@pytest.mark.parametrize(
    ("rule_id", "builder", "note"),
    EXEMPTION_CASES,
    ids=[f"{rule_id}-{note[:24]}" for rule_id, _, note in EXEMPTION_CASES],
)
def test_exemptions_stay_green(rule_id: str, builder, note: str, tmp_path: Path) -> None:
    """A rule's stated exemption is honoured rather than reported."""
    result = module_for(rule_id).run(builder(tmp_path))
    assert not result.findings, f"{rule_id} ignored its exemption: {note}"


@pytest.mark.parametrize(
    ("rule_id", "builder", "note"),
    STAGE_CASES,
    ids=[f"{rule_id}-stage" for rule_id, _, _ in STAGE_CASES],
)
def test_stage_level_violation_is_caught(rule_id: str, builder, note: str, tmp_path: Path) -> None:
    """A violation in a later stage is not hidden by a compliant earlier one."""
    result = module_for(rule_id).run(builder(tmp_path))
    assert result.findings, f"{rule_id} evaluated per package instead of per stage: {note}"
    assert any("phases[1]" in f.req_or_wp for f in result.findings)
