"""Acceptance ③ — a hard-coded-index fixture is rejected by the static scan.

The claim that indices resolve by name is an absence (no code depends on the qpos
layout), provable only statically. The scan must bite the violation fixture, leave
the name-resolved fixture untouched, and find the harness's own tree clean.
"""

from __future__ import annotations

from pathlib import Path

from sim.fkik.indexcheck import scan_source, scan_tree
from tests.wp0c04 import HARDCODED_INDEX_FIXTURE, NAME_RESOLVED_FIXTURE, REPO_ROOT


def test_violation_fixture_is_flagged() -> None:
    source = HARDCODED_INDEX_FIXTURE.read_text(encoding="utf-8")
    violations = scan_source(source, HARDCODED_INDEX_FIXTURE)
    arrays = {violation.array for violation in violations}
    # Both the slice and the scalar literal into qpos, plus the ctrl slice, are found.
    assert "qpos" in arrays
    assert "ctrl" in arrays
    assert len(violations) >= 3


def test_name_resolved_fixture_is_not_flagged() -> None:
    source = NAME_RESOLVED_FIXTURE.read_text(encoding="utf-8")
    assert scan_source(source, NAME_RESOLVED_FIXTURE) == []


def test_variable_index_is_not_flagged() -> None:
    # A variable index into a state array is the sanctioned name-resolved path.
    assert scan_source("adr = 3\nx = qpos[adr]\n", Path("ok.py")) == []


def test_resolution_table_index_is_not_flagged() -> None:
    # Indexing the resolution table by a literal id is not a state-array access.
    assert scan_source("a = model.jnt_qposadr[0]\n", Path("ok.py")) == []


def test_owning_tree_is_clean() -> None:
    assert scan_tree(REPO_ROOT / "sim" / "fkik") == []
