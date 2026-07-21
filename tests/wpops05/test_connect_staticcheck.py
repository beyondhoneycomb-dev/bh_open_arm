"""Acceptance ⑦ (static half) — `connect()` on a mode-transition path is flagged (F23).

The runtime guard only catches paths a run exercises; the static scan reads every line. It must
flag a `connect()` inside a mode-transition handler — whether marked with `@mode_transition` or
named like one — and must not fire on the legitimate initial-connect path.
"""

from __future__ import annotations

from pathlib import Path

from ops.telemetry.connect_staticcheck import find_connect_in_mode_transition

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TELEMETRY_PACKAGE = _REPO_ROOT / "ops" / "telemetry"
_FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_scan_flags_connect_on_transition_paths() -> None:
    """Both the decorated and the name-detected transition handlers are flagged."""
    violations = find_connect_in_mode_transition(_FIXTURES / "connect_in_transition.py")
    rules = " ".join(violation.rule for violation in violations)
    assert "switch_to_teleop" in rules
    assert "enter_mode_playback" in rules
    assert len(violations) == 2


def test_scan_does_not_fire_on_the_initial_connect() -> None:
    """A legitimate first connect and a reconnect-free transition produce no finding."""
    assert find_connect_in_mode_transition(_FIXTURES / "connect_clean.py") == []


def test_product_tree_has_no_connect_on_transition_paths() -> None:
    """The real telemetry package calls `connect()` on no mode-transition path."""
    assert find_connect_in_mode_transition(_TELEMETRY_PACKAGE) == []
