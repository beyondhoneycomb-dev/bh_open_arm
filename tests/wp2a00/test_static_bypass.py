"""Acceptance ④ — the real-send interlock tree has zero bypass paths, and the scan bites.

An interlock bypass is holding real-send authority without a genuine dry-run grant,
and its only shape in the consumer tree is fabricating a ``TransmissionGrant``. The
scan must be clean over the real ``backend/interlock`` tree and must catch both a
fabrication and a shadow ``interlock.py`` that would dodge the reused detector's
basename exemption. Legitimately *obtaining* a grant through the sanctioned minter is
not a bypass and stays unflagged.
"""

from __future__ import annotations

from pathlib import Path

from backend.interlock import find_grant_fabrication
from backend.interlock.staticcheck import RULE_SHADOW_INTERLOCK
from sim.dryrun.staticcheck import RULE_FABRICATED_GRANT

_REPO = Path(__file__).resolve().parents[2]
_INTERLOCK_TREE = _REPO / "backend" / "interlock"

_FABRICATION_SOURCE = (
    "from sim.dryrun.interlock import TransmissionGrant\n"
    "def forge() -> object:\n"
    "    return TransmissionGrant(object(), None, False, '')\n"
)
_LEGITIMATE_SOURCE = (
    "from sim.dryrun.interlock import authorize_transmission\n"
    "def obtain(verdict: object) -> object:\n"
    "    return authorize_transmission(verdict)\n"
)


def test_real_interlock_tree_has_no_grant_fabrication() -> None:
    """The shipped interlock tree fabricates no grant — zero bypass paths (④)."""
    assert find_grant_fabrication(_INTERLOCK_TREE) == ()


def test_fabricated_grant_is_flagged(tmp_path: Path) -> None:
    """A module minting a grant outside the sanctioned minter is caught — the scan bites."""
    (tmp_path / "sneaky.py").write_text(_FABRICATION_SOURCE, encoding="utf-8")
    findings = find_grant_fabrication(tmp_path)
    assert any(finding.rule == RULE_FABRICATED_GRANT for finding in findings)
    assert any(Path(finding.module).name == "sneaky.py" for finding in findings)


def test_legitimate_grant_acquisition_is_not_flagged(tmp_path: Path) -> None:
    """Obtaining a grant through `authorize_transmission` is the legitimate path, not a bypass."""
    (tmp_path / "clean.py").write_text(_LEGITIMATE_SOURCE, encoding="utf-8")
    assert find_grant_fabrication(tmp_path) == ()


def test_shadow_interlock_module_is_flagged(tmp_path: Path) -> None:
    """A file named interlock.py — exempt in the reused detector — is still caught here (④)."""
    (tmp_path / "interlock.py").write_text(_FABRICATION_SOURCE, encoding="utf-8")
    findings = find_grant_fabrication(tmp_path)
    assert any(finding.rule == RULE_SHADOW_INTERLOCK for finding in findings)
    assert any(Path(finding.module).name == "interlock.py" for finding in findings)
