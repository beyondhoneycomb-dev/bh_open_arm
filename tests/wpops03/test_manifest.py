"""The pin manifest distribution loads, validates, and does not duplicate upstream pins.

The committed manifest is the version-contract distribution: it must carry a
`contract_version`, an integer `generation`, and the four FR-SIM-102 pin sites, and it
must reference the LeRobot SHA and MuJoCo version as data rather than copying their
values (a copy is a second source of truth that drifts).
"""

from __future__ import annotations

from ops.versionpin.manifest import load_manifest, parse_minor, validate_manifest
from tests.wpops03.conftest import load_fixture


def test_committed_manifest_validates() -> None:
    report = validate_manifest(load_manifest())
    assert report.ok, report.problems
    assert report.contract_version == 1
    assert report.generation == 1


def test_manifest_missing_generation_is_rejected() -> None:
    manifest = load_manifest()
    del manifest["generation"]
    report = validate_manifest(manifest)
    assert not report.ok
    assert any("generation" in problem for problem in report.problems)


def test_manifest_missing_pin_is_rejected() -> None:
    manifest = load_manifest()
    del manifest["pins"]["isaac_sim"]
    report = validate_manifest(manifest)
    assert not report.ok
    assert any("isaac_sim" in problem for problem in report.problems)


def test_upstream_pins_are_referenced_not_duplicated() -> None:
    # The LeRobot SHA and MuJoCo version must not be re-stated as literal values in the
    # manifest; they are referenced by their owning artifact so there is one truth each.
    pins = load_manifest()["pins"]
    assert pins["lerobot"]["kind"] == "commit_sha"
    assert pins["lerobot"]["source"] == "deps/lerobot.pin"
    # No literal SHA/tree-hash value is copied into the manifest.
    assert not {"commit_sha", "sha", "tree_hash"} & set(pins["lerobot"])
    assert pins["mujoco"]["kind"] == "resolved"
    assert pins["mujoco"]["source"] == "uv.lock"
    # No literal MuJoCo version is copied into the manifest.
    assert "version" not in pins["mujoco"]


def test_parse_minor_reads_the_minor_line() -> None:
    assert parse_minor("5.1.0") == (5, 1)
    assert parse_minor("==5.1.0") == (5, 1)
    assert parse_minor("2.3.x") == (2, 3)
    assert parse_minor("==2.3.*") == (2, 3)


def test_prior_generation_fixture_is_one_step_back() -> None:
    prior = validate_manifest(load_fixture("prior_generation.yaml"))
    assert prior.ok, prior.problems
    assert prior.generation == 0
