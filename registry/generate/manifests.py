"""Emit one machine-readable manifest per work package.

A manifest is what a workflow reads to find out what it is executing: the six
elements of `00` §3.2 in field form. It is a projection of
`registry/traceability.yaml`, never a second source — where the two disagree
the registry wins (`05` §0.1), and `verify_manifest` is the executable form of
that rule.

The manifest deliberately carries fewer fields than the registry record. Only
the axes a workflow needs in order to run are projected; copying the rest would
make the manifest a second registry, which is the exact failure the acceptance
criterion "두 정본 방지" names.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from registry.generate.source import Record, WorkPackage, canonical_json

SCHEMA_PATH = Path(__file__).with_name("manifest.schema.json")

# Relative to the build directory, so the caller decides where the tree lands.
MANIFEST_SUBDIR = "manifests"

# Projected axes and the registry field each one reads. `consumes`/`produces`
# live under the `contract` key in the registry but are flat in the manifest,
# so they are resolved through the collapsed WorkPackage view instead.
AXIS_SOURCE = {
    "owns": "owns",
    "consumes": "consumes",
    "produces": "produces",
    "gates": "gates",
    "normalization_hash": "normalization_hash",
    "env_hash": "env_hash",
}


class ManifestSchemaError(Exception):
    """Raised when a generated manifest violates the manifest schema."""


def load_validator() -> Draft202012Validator:
    """Build the manifest schema validator.

    Returns:
        Draft202012Validator: Validator bound to `manifest.schema.json`.
    """
    with SCHEMA_PATH.open(encoding="utf-8") as handle:
        schema: dict[str, Any] = json.load(handle)
    return Draft202012Validator(schema)


def schema_errors(manifest: Record) -> list[str]:
    """Collect every schema violation in a manifest.

    Args:
        manifest: Candidate manifest object.

    Returns:
        list[str]: One message per violation, ordered by path; empty when valid.
    """
    return _format_errors(load_validator(), manifest)


def _format_errors(validator: Draft202012Validator, manifest: Record) -> list[str]:
    """Render a validator's findings as sorted, path-prefixed messages.

    Args:
        validator: Validator bound to the manifest schema.
        manifest: Candidate manifest object.

    Returns:
        list[str]: One message per violation, ordered by path.
    """
    ordered = sorted(validator.iter_errors(manifest), key=lambda err: list(err.absolute_path))
    return [
        f"{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in ordered
    ]


def build_manifest(package: WorkPackage) -> Record:
    """Project one work package onto its manifest.

    `normalization_hash` and `env_hash` are always written, `null` included:
    the slot is dug here so that `WP-N1-04` and `WP-ENV-04` have somewhere to
    enforce a value later (`02a` §−2.3 acceptance ⑦).

    Args:
        package: Collapsed registry view of the package.

    Returns:
        Record: The manifest object, ready to serialize.
    """
    manifest: Record = {
        "wp_id": package.wp_id,
        "owns": package.owns,
        "consumes": package.consumes,
        "produces": package.produces,
        "gates": package.gates,
        "normalization_hash": package.normalization_hash,
        "env_hash": package.env_hash,
    }
    if package.is_multi_stage:
        manifest["phases"] = package.phases
    else:
        manifest["workflow"] = package.workflow
        manifest["exec_class"] = package.exec_class
    return manifest


def verify_manifest(manifest: Record, package: WorkPackage) -> list[str]:
    """Compare a manifest against the registry on every projected axis.

    Args:
        manifest: Manifest object, as loaded from disk or built.
        package: Collapsed registry view of the same package.

    Returns:
        list[str]: One message per axis that disagrees; empty when they match.
    """
    mismatches: list[str] = []
    if manifest.get("wp_id") != package.wp_id:
        return [f"wp_id: manifest {manifest.get('wp_id')!r} != registry {package.wp_id!r}"]

    for axis, attribute in AXIS_SOURCE.items():
        expected = getattr(package, attribute)
        if manifest.get(axis) != expected:
            mismatches.append(f"{axis}: manifest {manifest.get(axis)!r} != registry {expected!r}")

    if package.is_multi_stage:
        if manifest.get("phases") != package.phases:
            mismatches.append(
                f"phases: manifest {manifest.get('phases')!r} != registry {package.phases!r}"
            )
        for scalar in ("workflow", "exec_class"):
            if scalar in manifest:
                mismatches.append(f"{scalar}: present on a multi-stage package")
    else:
        for scalar, expected_scalar in (
            ("workflow", package.workflow),
            ("exec_class", package.exec_class),
        ):
            if manifest.get(scalar) != expected_scalar:
                mismatches.append(
                    f"{scalar}: manifest {manifest.get(scalar)!r} != registry {expected_scalar!r}"
                )
        if "phases" in manifest:
            mismatches.append("phases: present on a single-stage package")

    return mismatches


def render_manifests(packages: list[WorkPackage]) -> dict[str, str]:
    """Render every manifest as build-relative path to file text.

    Rendering to text rather than to disk lets `--check` compare without
    writing, so the check cannot repair the drift it is meant to report.

    Every manifest is validated against its own schema before it is rendered.
    A generator that can emit a manifest its schema rejects would make the
    schema decorative for exactly the records the schema exists to constrain.

    Args:
        packages: Collapsed registry views, one per package.

    Returns:
        dict[str, str]: Build-relative path to serialized manifest.

    Raises:
        ManifestSchemaError: If a generated manifest violates the schema.
    """
    validator = load_validator()
    rendered: dict[str, str] = {}
    for package in packages:
        manifest = build_manifest(package)
        errors = _format_errors(validator, manifest)
        if errors:
            raise ManifestSchemaError(f"{package.wp_id}: " + "; ".join(errors))
        rendered[f"{MANIFEST_SUBDIR}/{package.wp_id}.json"] = canonical_json(manifest)
    return rendered
