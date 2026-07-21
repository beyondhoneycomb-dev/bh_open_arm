"""Acceptance ① (static half) — no consumer reaches Kinematics off the ordered path.

The runtime state machine enforces the order for callers that use ``OrderedIkBuild``;
this scan enforces that no one goes around it. A fixture that constructs Kinematics
directly must be flagged, the owning tree must be exempt, and the product consumer
trees must currently be clean.
"""

from __future__ import annotations

from pathlib import Path

from sim.ik.staticcheck import scan_source, scan_tree
from tests.wp0c02 import ORDER_VIOLATION_FIXTURE, REPO_ROOT

# Product trees that consume IK and must never construct Kinematics directly. Tests
# are excluded on purpose: a test may legitimately import IKParams to build fixtures.
PRODUCT_TREES = ("backend", "packages", "contracts", "ops", "dashboard")


def test_violation_fixture_is_flagged() -> None:
    source = ORDER_VIOLATION_FIXTURE.read_text(encoding="utf-8")
    violations = scan_source(source, ORDER_VIOLATION_FIXTURE)
    symbols = {violation.symbol for violation in violations}
    # Both the symbol import and the direct construction are caught; IKParams is not.
    assert "Kinematics" in symbols
    assert "IKParams" not in symbols
    assert len(violations) >= 2


def test_ikparams_import_alone_is_not_flagged() -> None:
    source = "from openarm_control.kinematics import IKParams\np = IKParams()\n"
    assert scan_source(source, Path("ok.py")) == []


def test_owning_tree_is_exempt() -> None:
    assert scan_tree(REPO_ROOT / "sim" / "ik") == []


def test_product_trees_are_clean() -> None:
    for tree in PRODUCT_TREES:
        root = REPO_ROOT / tree
        if root.is_dir():
            assert scan_tree(root) == [], f"order violation found under {tree}/"
