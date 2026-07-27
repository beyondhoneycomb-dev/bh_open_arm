"""WP-4B-01 CG-4B-01f: no hardcoded capability constant survives in the engine.

The static check must BITE (a fixture with a copied ceiling is caught) and stay
clean on the real engine (no ceiling was copied). Both halves are required: a
scanner that never fires is indistinguishable from a scanner that always passes.
"""

from __future__ import annotations

from backend.compat.policy_matrix import (
    forbidden_capability_values,
    scan_package,
    scan_source,
)

# A source snippet that copies the 32-dim ceiling into a literal — the positive
# control proving the scanner fires rather than passing vacuously.
_HARDCODED_SOURCE = "def capability():\n    return {'max_state_dim': 32, 'max_action_dim': 32}\n"

# A source snippet that reads the ceiling from a config object instead of restating
# it — the negative control the scanner must leave clean.
_INTROSPECTED_SOURCE = (
    "def capability(config):\n    return {'max_state_dim': config.max_state_dim}\n"
)


def test_forbidden_set_is_the_live_introspected_ceilings() -> None:
    """The forbidden values are the ceilings the installed configs declare."""
    forbidden = forbidden_capability_values()
    assert 32 in forbidden
    assert 132 in forbidden


def test_scanner_bites_on_a_copied_ceiling() -> None:
    """CG-4B-01f positive control: a literal 32 is found."""
    findings = scan_source(_HARDCODED_SOURCE, forbidden_capability_values())
    assert [finding.value for finding in findings] == [32, 32]


def test_scanner_is_clean_on_introspected_source() -> None:
    """CG-4B-01f negative control: reading from a config is not flagged."""
    findings = scan_source(_INTROSPECTED_SOURCE, forbidden_capability_values())
    assert findings == []


def test_engine_holds_no_hardcoded_capability_constant() -> None:
    """CG-4B-01f: the engine's own source restates no live capability ceiling."""
    findings = scan_package()
    assert findings == [], f"hardcoded capability constants found: {findings}"
