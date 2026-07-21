"""The policy_compat.yaml registry is faithful, and the checker that says so bites.

`load_registry` must parse every policy, and `verify_against_introspection` must
pass on the real registry while FAILING on a drifted one — a checker that cannot
fail is worthless. This suite proves both: the on-disk registry is clean, and each
kind of drift (wrong ceiling, bogus guard predicate, non-fleet target) is caught.
"""

from __future__ import annotations

import dataclasses

import pytest

from backend.policy_matrix import load_registry, verify_against_introspection
from backend.policy_matrix.registry import BlockedPath


def test_registry_loads_all_four_policies() -> None:
    """The four ranked families are present with two-field block reasons."""
    entries = {entry.policy: entry for entry in load_registry()}
    assert set(entries) == {"smolvla", "pi0", "pi05", "groot"}
    for entry in entries.values():
        assert entry.block_reason.code
        assert entry.block_reason.human
        assert entry.supported_targets


def test_clean_registry_passes() -> None:
    """The on-disk registry matches introspection, guards and targets."""
    assert verify_against_introspection(load_registry()) == ()


def test_drifted_ceiling_is_caught() -> None:
    """A recorded ceiling that disagrees with introspection is reported."""
    entries = list(load_registry())
    smolvla = next(e for e in entries if e.policy == "smolvla")
    drifted = dataclasses.replace(smolvla, max_state_dim=9999)
    problems = verify_against_introspection((drifted,))
    assert any("max_state_dim" in p for p in problems)


def test_bogus_guard_predicate_is_caught() -> None:
    """A blocked_path naming a non-existent guard is reported."""
    entries = list(load_registry())
    groot = next(e for e in entries if e.policy == "groot")
    drifted = dataclasses.replace(
        groot,
        blocked_paths=(
            BlockedPath(name="x", predicate="targets.guards.no_such_guard", rationale=""),
        ),
    )
    problems = verify_against_introspection((drifted,))
    assert any("does not resolve to a callable guard" in p for p in problems)


def test_non_fleet_target_is_caught() -> None:
    """A supported target that is not a fleet target is reported."""
    entries = list(load_registry())
    smolvla = next(e for e in entries if e.policy == "smolvla")
    drifted = dataclasses.replace(smolvla, supported_targets=("a100",))
    problems = verify_against_introspection((drifted,))
    assert any("not a fleet target" in p for p in problems)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
