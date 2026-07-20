"""Manifest coverage and registry agreement.

Acceptance criteria `02a` §−2.3 `WP-BOOT-02` ① (every work package has a
manifest) and ② (manifest and registry agree on every projected axis, and a
disagreeing fixture is rejected).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from registry.generate.manifests import (
    MANIFEST_SUBDIR,
    ManifestSchemaError,
    build_manifest,
    render_manifests,
    schema_errors,
    verify_manifest,
)
from registry.generate.source import (
    RegistryDriftError,
    WorkPackage,
    group_by_work_package,
)
from registry.ingest.catalog import parse_all

CATALOGS = Path(__file__).resolve().parents[2] / "docs" / "plan"


# ① every work package has a manifest.


def test_every_work_package_has_a_manifest(packages: list[WorkPackage]) -> None:
    """Rendered manifests cover the package set exactly, with none missing."""
    rendered = render_manifests(packages)
    expected = {f"{MANIFEST_SUBDIR}/{package.wp_id}.json" for package in packages}
    assert set(rendered) == expected


def test_manifest_count_matches_the_issuing_catalogs(packages: list[WorkPackage]) -> None:
    """Coverage is measured against the catalogs that issue the ids, not the registry alone.

    Counting manifests against the registry alone would be circular: a package
    dropped during seeding would be absent from both sides and the count would
    still agree.
    """
    issued = {entry.wp_id for entry in parse_all(CATALOGS)}
    assert {package.wp_id for package in packages} == issued


def test_manifests_land_one_file_per_package(packages: list[WorkPackage], tmp_path: Path) -> None:
    """Each manifest is a separate file named for its package."""
    rendered = render_manifests(packages)
    for relative, content in rendered.items():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    for package in packages:
        loaded = json.loads(
            (tmp_path / MANIFEST_SUBDIR / f"{package.wp_id}.json").read_text(encoding="utf-8")
        )
        assert loaded["wp_id"] == package.wp_id


# ② manifest and registry agree on every projected axis.


def test_generated_manifests_agree_with_the_registry(packages: list[WorkPackage]) -> None:
    """Every generated manifest matches its registry records on every axis."""
    for package in packages:
        assert verify_manifest(build_manifest(package), package) == []


@pytest.mark.parametrize(
    ("axis", "value"),
    [
        ("gates", ["CG-9Z-99z"]),
        ("owns", [{"glob": "somewhere/else/**", "mode": "EXCLUSIVE"}]),
        ("consumes", ["CTR-WS@v1"]),
        ("produces", ["CTR-WS@v1"]),
        ("env_hash", "sha256:" + "1" * 64),
        ("normalization_hash", "sha256:" + "2" * 64),
        ("wp_id", "WP-0C-01"),
    ],
)
def test_axis_disagreement_is_rejected(packages: list[WorkPackage], axis: str, value: Any) -> None:
    """A manifest that diverges from the registry on any axis is rejected."""
    package = _package(packages, "WP-BOOT-02")
    manifest = build_manifest(package)
    manifest[axis] = value
    assert verify_manifest(manifest, package) != []


def test_shape_swap_is_rejected(packages: list[WorkPackage]) -> None:
    """A single-stage manifest may not silently claim the other shape kind."""
    package = _package(packages, "WP-BOOT-02")
    manifest = build_manifest(package)
    del manifest["workflow"]
    del manifest["exec_class"]
    manifest["phases"] = [
        {
            "workflow": "SHAPE-CF",
            "exec_class": "AI-offline",
            "owns": [],
            "cancel_policy": "finish-step",
            "after": None,
        },
        {
            "workflow": "SHAPE-MS",
            "exec_class": "AI-on-HW",
            "owns": [],
            "cancel_policy": "latch-to-hold",
            "after": 0,
        },
    ]
    assert verify_manifest(manifest, package) != []


def test_multi_stage_manifest_may_not_carry_scalars(packages: list[WorkPackage]) -> None:
    """A multi-stage manifest that also declares the scalars is rejected."""
    package = _package(packages, "WP-1-03")
    manifest = build_manifest(package)
    manifest["workflow"] = "SHAPE-CF"
    assert verify_manifest(manifest, package) != []


def test_generation_fails_on_a_schema_violating_package(packages: list[WorkPackage]) -> None:
    """The generator refuses to emit a manifest its own schema would reject."""
    package = _package(packages, "WP-BOOT-02")
    broken = WorkPackage(**{**vars(package), "gates": ["PG-RT-001"]})
    with pytest.raises(ManifestSchemaError):
        render_manifests([broken])


# ⑧ the generated corpus itself carries no sealed gate id.


def test_generated_corpus_validates_against_its_own_schema(
    packages: list[WorkPackage],
) -> None:
    """Every one of the real manifests satisfies the manifest schema."""
    for package in packages:
        assert schema_errors(build_manifest(package)) == [], package.wp_id


def test_generated_corpus_carries_no_sealed_gate_id(packages: list[WorkPackage]) -> None:
    """No gate-bearing field in the real corpus holds a bare PG-RT-001 or an M-8.

    The fixtures prove the rule can fail; this proves it currently holds on the
    corpus the rule governs. A rule that is only ever exercised on fixtures
    says nothing about the tree it is supposed to protect.
    """
    sealed = {"PG-RT-001", "M-8"}
    for package in packages:
        manifest = build_manifest(package)
        for field in ("gates", "exit_gates", "requires_gates"):
            assert sealed.isdisjoint(manifest.get(field, [])), f"{package.wp_id}.{field}"


# Package-level fields must agree across the records of one package (CI-14c class A).


def test_package_level_drift_is_rejected(registry_document: dict[str, Any]) -> None:
    """Two records of one package asserting different gates abort the collapse."""
    entries = [dict(record) for record in registry_document["entries"]]
    twins = [record for record in entries if record["wp"] == "WP-3A-01"]
    assert len(twins) >= 2, "fixture needs a package with at least two records"
    twins[0]["gate"] = [*twins[0]["gate"], "CG-3A-01z"]
    with pytest.raises(RegistryDriftError):
        group_by_work_package({**registry_document, "entries": entries})


def test_package_level_agreement_is_accepted(registry_document: dict[str, Any]) -> None:
    """The untouched registry collapses without drift."""
    assert group_by_work_package(registry_document)


def _package(packages: list[WorkPackage], wp_id: str) -> WorkPackage:
    """Look up one package view by id.

    Args:
        packages: Collapsed registry views.
        wp_id: Package id to find.

    Returns:
        WorkPackage: The matching view.
    """
    return next(package for package in packages if package.wp_id == wp_id)
