"""Acceptance ② — a manifest with no (or a stale) normalization hash is refused start.

The barrier is the launch-side of the Wave -1 blocking barrier: `WP-BOOT-02` digs
the manifest slot, and this refuses to start a package that leaves it empty or
cites a superseded value.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from registry.normalization.barrier import (
    REASON_ABSENT,
    REASON_MISMATCH,
    check_manifest,
)
from registry.normalization.cli import EXIT_OK, EXIT_VIOLATIONS, main
from registry.normalization.content_hash import ISSUED_PATH, read_issued

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "registry" / "normalization" / "fixtures"
NO_HASH = FIXTURE_DIR / "manifest_no_hash.yaml"
STALE_HASH = FIXTURE_DIR / "manifest_stale_hash.yaml"

ISSUED = read_issued(ISSUED_PATH) or ""


def _load(path: Path) -> dict[str, object]:
    """Read a manifest fixture."""
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_manifest_without_hash_is_blocked() -> None:
    """The violation fixture: no normalization_hash field blocks start."""
    verdict = check_manifest(_load(NO_HASH), ISSUED)
    assert verdict.blocked
    assert verdict.reason == REASON_ABSENT
    assert verdict.declared is None


def test_manifest_with_stale_hash_is_blocked() -> None:
    """A cited hash that is not the issued hash blocks start."""
    verdict = check_manifest(_load(STALE_HASH), ISSUED)
    assert verdict.blocked
    assert verdict.reason == REASON_MISMATCH
    assert verdict.declared != ISSUED


def test_manifest_with_current_hash_is_cleared() -> None:
    """A manifest citing the issued hash clears the barrier."""
    manifest = {"wp_id": "WP-OK-01", "normalization_hash": ISSUED}
    verdict = check_manifest(manifest, ISSUED)
    assert not verdict.blocked
    assert verdict.reason == ""


def test_empty_string_hash_is_blocked() -> None:
    """A present-but-empty field is no declaration."""
    manifest = {"wp_id": "WP-EMPTY-01", "normalization_hash": ""}
    verdict = check_manifest(manifest, ISSUED)
    assert verdict.blocked
    assert verdict.reason == REASON_ABSENT


def test_cli_barrier_rejects_the_no_hash_fixture() -> None:
    """`--barrier` exits non-zero on the violation fixture."""
    assert main(["--barrier", str(NO_HASH), "--root", str(REPO_ROOT)]) == EXIT_VIOLATIONS


def test_cli_barrier_rejects_the_stale_fixture() -> None:
    """`--barrier` exits non-zero on a stale-hash manifest."""
    assert main(["--barrier", str(STALE_HASH), "--root", str(REPO_ROOT)]) == EXIT_VIOLATIONS


def test_cli_barrier_clears_a_current_manifest(tmp_path: Path) -> None:
    """`--barrier` exits zero on a manifest citing the issued hash."""
    manifest = tmp_path / "ok.yaml"
    manifest.write_text(
        yaml.safe_dump({"wp_id": "WP-OK-02", "normalization_hash": ISSUED}),
        encoding="utf-8",
    )
    assert main(["--barrier", str(manifest), "--root", str(REPO_ROOT)]) == EXIT_OK
