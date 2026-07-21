"""Acceptance ④ — the Isaac pin is Sim 5.1 / Lab 2.3.x with zero auto-upgrade.

The committed manifest must assert clean; a manifest whose Isaac pins have been advanced
to the forbidden 6.0 / Newton / 3.0-beta track must be rejected, so the assertion is a
real gate against a silent 5.1 -> 6.0 / 2.3 -> 3.0 upgrade rather than a formality.
"""

from __future__ import annotations

from ops.versionpin.manifest import assert_isaac_pin, load_manifest
from tests.wpops03.conftest import load_fixture


def test_committed_isaac_pin_is_5_1_and_2_3_x() -> None:
    report = assert_isaac_pin(load_manifest())
    assert report.ok, report.problems
    assert report.isaac_sim == "5.1.0"
    assert report.isaac_lab == "2.3.x"


def test_auto_upgraded_isaac_pin_is_rejected() -> None:
    report = assert_isaac_pin(load_fixture("isaac_autoupgraded.yaml"))
    assert not report.ok
    # Both off-line versions are named, not just the first.
    joined = " ".join(report.problems)
    assert "Isaac Sim" in joined
    assert "Isaac Lab" in joined


def test_isaac_sim_minor_drift_is_rejected() -> None:
    manifest = load_manifest()
    manifest["pins"]["isaac_sim"]["version"] = "5.2.0"
    manifest["pins"]["isaac_sim"]["spec"] = "==5.2.0"
    report = assert_isaac_pin(manifest)
    assert not report.ok
    assert any("Isaac Sim" in problem for problem in report.problems)


def test_isaac_lab_range_spec_is_rejected() -> None:
    # Even on the right minor line, a range spec would let a resolver auto-upgrade.
    manifest = load_manifest()
    manifest["pins"]["isaac_lab"]["spec"] = ">=2.3"
    report = assert_isaac_pin(manifest)
    assert not report.ok
    assert any("isaac_lab" in problem and "auto-upgrade" in problem for problem in report.problems)


def test_missing_forbidden_upgrades_is_rejected() -> None:
    # The 6.0/Newton/3.0-beta ban must be documented, not implied.
    manifest = load_manifest()
    manifest["forbidden_upgrades"] = []
    report = assert_isaac_pin(manifest)
    assert not report.ok
    assert any("forbidden_upgrades" in problem for problem in report.problems)
