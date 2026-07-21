"""Acceptance ⑪ — the ceiling is the introspected value, routed through WP-ENV-04.

The dimension ceiling must be the value the pinned upstream actually declares, the
same value the WP-ENV-04 predicate guards — never a literal `32` written into the
matrix. This suite proves the ceiling is introspected off the installed config, that
the WP-ENV-04 `max_state_dim=32` fact still holds on the pin, that the registry's
recorded ceilings match introspection, and — structurally — that no cap literal is
hardcoded in the calculator or the resolver.
"""

from __future__ import annotations

import pytest

from backend.policy_matrix import (
    introspect_caps,
    load_registry,
    verify_against_introspection,
    verify_env04_predicate,
)
from tests.wp0c08 import POLICY_MATRIX_DIR, numeric_literals

# The cap ceilings are never a source literal; a `32`/`132` written into the
# calculator or resolver logic would mean the ceiling was hardcoded instead of
# introspected. (A mention in a docstring or the `..._default_32` symbol name is
# not a code literal and is deliberately not counted.)
_CALCULATOR_FILES = ("caps.py", "matrix.py")
_CAP_LITERALS = {32.0, 132.0}


def test_smolvla_ceiling_is_introspected_thirty_two() -> None:
    """The 32-dim ceiling comes from the installed config, and GR00T's is 132."""
    assert introspect_caps("smolvla").max_state_dim == 32
    assert introspect_caps("smolvla").max_action_dim == 32
    assert introspect_caps("groot").max_state_dim == 132


def test_env04_predicate_still_holds() -> None:
    """⑪ — the WP-ENV-04 fact the ceiling routes through is intact on the pin."""
    assert verify_env04_predicate() == ()


def test_registry_ceilings_match_introspection() -> None:
    """⑪ — every recorded ceiling equals what the config declares; no drift."""
    assert verify_against_introspection(load_registry()) == ()


def test_ceiling_is_not_a_source_literal() -> None:
    """⑪ — no `32`/`132` cap literal is hardcoded in the calculator or resolver."""
    for filename in _CALCULATOR_FILES:
        used = numeric_literals(POLICY_MATRIX_DIR / filename)
        assert not (used & _CAP_LITERALS), (
            f"hardcoded cap literal in {filename}: {used & _CAP_LITERALS}"
        )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
