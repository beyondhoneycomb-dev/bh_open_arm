"""Acceptance ⑤ — the lock path is one contract-versioned value, not two copies.

`01` FR-SYS-005 says `/var/lock`, `02` FR-CON-010 says `/run/lock`; these are one
inode on a systemd host (`/var/lock` is a symlink). The reconciliation lives once in
`paths.py`, and the static check proves no divergent second definition exists in the
lock tree.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.can.lock import (
    CANONICAL_LOCK_DIR,
    LEGACY_LOCK_DIR_SYMLINK,
    LOCK_PATH_CONTRACT,
    InterfaceNameError,
    normalize_lock_path,
)
from backend.can.lock.staticcheck import find_divergent_lock_paths

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LOCK_PACKAGE = _REPO_ROOT / "backend" / "can" / "lock"
_FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_normalize_builds_the_canonical_shape(tmp_path: Path) -> None:
    """The file-name template is fixed; only the directory is injectable."""
    assert normalize_lock_path("can0", str(tmp_path)) == tmp_path / "openarm-can0.lock"


def test_canonical_default_is_run_lock() -> None:
    """The default directory is the single canonical value `02` FR-CON-010 names."""
    assert CANONICAL_LOCK_DIR == "/run/lock"
    assert normalize_lock_path("can0") == Path("/run/lock/openarm-can0.lock")


def test_legacy_dir_is_recorded_as_an_alias_only() -> None:
    """`/var/lock` is documented as the symlink alias, not a second path value."""
    assert LEGACY_LOCK_DIR_SYMLINK == "/var/lock"
    assert LEGACY_LOCK_DIR_SYMLINK != CANONICAL_LOCK_DIR


def test_contract_version_is_pinned() -> None:
    """The path shape is versioned so a change is a bump, not a silent edit."""
    assert LOCK_PATH_CONTRACT == "CTR-LOCK@v1"


@pytest.mark.parametrize("bad", ["../evil", "a/b", "", ".", ".."])
def test_interface_name_cannot_escape_the_lock_dir(bad: str) -> None:
    """An interface name is a path component only; separators and dot-names are refused."""
    with pytest.raises(InterfaceNameError):
        normalize_lock_path(bad)


def test_lock_path_is_single_valued_in_source() -> None:
    """No `openarm-…lock` or lock-dir literal exists outside the single authority.

    This is acceptance ⑤ proper: the `01`/`02` disagreement must not survive as two
    hardcoded copies in code.
    """
    assert find_divergent_lock_paths(_LOCK_PACKAGE) == []


def test_divergent_path_fixture_is_caught() -> None:
    """The single-value scan actually bites: a hardcoded copy is flagged."""
    findings = find_divergent_lock_paths(_FIXTURES / "divergent_lock_path.py")
    assert findings, "the divergent-path scan must flag a hardcoded lock path"
