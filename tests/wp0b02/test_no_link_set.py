"""Acceptance ⑤ — no code path configures a CAN link (`ip link set`), and the scan bites.

FR-SYS-006 forbids code from setting the link. `find_link_set_calls` is an AST scan for
process spawns whose arguments form an `ip link set` mutation. The CAN tree must be clean;
the violation fixture proves the scan is not vacuous; the verify-only fixture proves it
does not over-fire on guidance strings.
"""

from __future__ import annotations

from pathlib import Path

from backend.can.link.staticcheck import find_link_set_calls

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CAN_TREE = _REPO_ROOT / "backend" / "can"
_FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_can_tree_has_no_link_set_call() -> None:
    """No process spawn sets a link anywhere under backend/can (the codebase claim)."""
    assert find_link_set_calls(_CAN_TREE) == []


def test_violation_fixture_is_caught() -> None:
    """The scan bites: an actual `ip link set` exec is flagged."""
    findings = find_link_set_calls(_FIXTURES / "link_set_call.py")
    assert findings, "the link-set scan must flag a real ip-link-set exec"
    assert findings[0].symbol == "subprocess.run"


def test_guidance_string_is_not_a_violation() -> None:
    """A returned command string is data, not a mutation — no finding."""
    assert find_link_set_calls(_FIXTURES / "link_verify_only.py") == []
