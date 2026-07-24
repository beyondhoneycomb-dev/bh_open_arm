"""WP-3C-07 ③/⑤ static half: the source itself never re-stamps and never auto-saves.

The two structural invariants — no `stamp_repo_id()` on resume (⑤) and no auto-save on
recovery (③) — are held by an AST scan over the package source, and the scan must both
pass on the real tree and *bite* on planted violations. A checker that never fires is a
fake green, so the bite tests plant a re-stamp call and each auto-save call and assert
each is flagged with the right rule.
"""

from __future__ import annotations

from pathlib import Path

import backend.crash_recovery
from backend.crash_recovery.staticcheck import (
    RULE_NO_AUTO_SAVE,
    RULE_NO_RESTAMP,
    scan_source,
    scan_tree,
)

_PACKAGE_DIR = Path(backend.crash_recovery.__file__).parent


def test_package_source_has_no_forbidden_calls() -> None:
    """The real package tree is clean: no re-stamp, no auto-save call anywhere."""
    assert scan_tree(_PACKAGE_DIR) == ()


def test_scan_bites_on_a_planted_restamp_call() -> None:
    """A planted `stamp_repo_id()` call is flagged under the no-restamp rule."""
    bad = "def resume(repo_id):\n    return stamp_repo_id(repo_id)\n"

    violations = scan_source(bad, "planted.py")

    assert len(violations) == 1
    assert violations[0].symbol == "stamp_repo_id"
    assert violations[0].rule == RULE_NO_RESTAMP
    assert violations[0].line == 2


def test_scan_bites_on_a_planted_save_episode_call() -> None:
    """A planted `dataset.save_episode()` call is flagged under the no-auto-save rule."""
    bad = "def recover(dataset):\n    dataset.save_episode()\n"

    violations = scan_source(bad, "planted.py")

    assert len(violations) == 1
    assert violations[0].symbol == "save_episode"
    assert violations[0].rule == RULE_NO_AUTO_SAVE


def test_scan_bites_on_planted_label_acceptance_calls() -> None:
    """Every `EpisodeLabel` acceptance call — judged/suggested/with_manual/with_auto — bites."""
    bad = (
        "def accept(label):\n"
        "    a = EpisodeLabel.judged(0)\n"
        "    b = EpisodeLabel.suggested(0, v)\n"
        "    c = label.with_manual(v)\n"
        "    d = label.with_auto(v)\n"
        "    return a, b, c, d\n"
    )

    violations = scan_source(bad, "planted.py")

    flagged = {violation.symbol for violation in violations}
    assert flagged == {"judged", "suggested", "with_manual", "with_auto"}
    assert all(violation.rule == RULE_NO_AUTO_SAVE for violation in violations)


def test_scan_ignores_forbidden_names_in_strings_and_comments() -> None:
    """A forbidden name in a docstring or string is not a call and is not flagged."""
    benign = (
        '"""This module must never call stamp_repo_id or save_episode."""\n'
        "MESSAGE = 'do not save_episode here'\n"
    )

    assert scan_source(benign, "benign.py") == ()
