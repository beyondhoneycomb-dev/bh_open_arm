"""Static checks over stored rule text: can-prefix ban (⑦) and one-axis rejection.

Each scan ships with a violation fixture proving it actually bites, plus the clean
fixture proving it does not over-reject.
"""

from __future__ import annotations

from pathlib import Path

from ops.hw.udev.staticcheck import find_can_prefixed_names, find_single_axis_rules

_RULES = Path(__file__).resolve().parent / "fixtures" / "rules"


def _read(name: str) -> str:
    return (_RULES / name).read_text(encoding="utf-8")


def test_can_prefix_fixture_is_rejected() -> None:
    """Acceptance ⑦: a rules file naming interfaces `canN` is flagged."""
    findings = find_can_prefixed_names(_read("bad_can_prefix.rules"))
    assert len(findings) == 2
    assert all("starts with 'can'" in str(finding) for finding in findings)


def test_good_ruleset_has_no_can_prefix() -> None:
    """The clean two-axis fixture triggers no can-prefix finding (no over-reject)."""
    assert find_can_prefixed_names(_read("good_two_axis.rules")) == []


def test_single_axis_rules_are_rejected() -> None:
    """Contract: a rule missing either axis is flagged at store time."""
    findings = find_single_axis_rules(_read("single_axis.rules"))
    assert len(findings) == 2
    reasons = " ".join(str(finding) for finding in findings)
    assert "channel axis (ATTR{dev_id})" in reasons
    assert "adapter axis (ATTRS{serial} or KERNELS)" in reasons


def test_two_axis_rules_pass_the_store_guard() -> None:
    """The correct four-entry rule set is accepted (no single-axis finding)."""
    assert find_single_axis_rules(_read("good_two_axis.rules")) == []


def test_can_prefixed_but_two_axis_is_still_rejected_by_name_scan() -> None:
    """A rule can be two-axis yet still illegal by name — the scans are independent."""
    text = _read("bad_can_prefix.rules")
    assert find_single_axis_rules(text) == []
    assert find_can_prefixed_names(text)
