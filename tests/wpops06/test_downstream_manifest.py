"""Downstream-consumer acceptance: every referenced code resolves in the registry.

Acceptance ⑫. A consumer manifest that names error codes it may emit must name
only codes the frozen registry defines; an unresolved reference means a consumer
would emit a code with no recovery procedure. This is the exit-gate property —
`WP-3A-00` / `WP-G-01` / `WP-G-03` consume CTR-ERR@v1, so a dangling code stops
them starting.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from contracts.errors.checkers import check_coverage
from contracts.errors.registry import REGISTRY


def _referenced_codes(manifest: Path) -> set[str]:
    """Return the error codes a consumer manifest declares it references.

    Args:
        manifest: A YAML manifest with a `referenced_codes` list.

    Returns:
        (set[str]) The referenced code strings.
    """
    body = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    return set(body.get("referenced_codes", []) or [])


def test_resolvable_manifest_has_no_unresolved(tmp_path: Path) -> None:
    """A manifest referencing only registered codes resolves fully (acceptance ⑫)."""
    manifest = tmp_path / "consumer.yaml"
    manifest.write_text(
        yaml.safe_dump({"referenced_codes": ["OA-CAN-004", "OA-MOT-00E", "OA-SYS-004"]}),
        encoding="utf-8",
    )
    assert check_coverage(REGISTRY, _referenced_codes(manifest)) == []


def test_dangling_reference_is_reported(tmp_path: Path) -> None:
    """A manifest naming an unregistered code is caught (acceptance ⑫)."""
    manifest = tmp_path / "consumer.yaml"
    manifest.write_text(
        yaml.safe_dump({"referenced_codes": ["OA-CAN-004", "OA-GHOST-042"]}),
        encoding="utf-8",
    )
    findings = check_coverage(REGISTRY, _referenced_codes(manifest))
    assert [f.subject for f in findings] == ["OA-GHOST-042"]
