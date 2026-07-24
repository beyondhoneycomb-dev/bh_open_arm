"""WP-3D-07 ④: merging an imported artifact with a native one is REFUSED.

`02b` §8.2 WP-3D-07 ③ / `FR-DAT-041`: the two families must not be merged. This module
checks the merge guard refuses any pairing that includes a legacy-imported dataset —
imported+native and imported+imported — while allowing native+native, and that the
non-raising eligibility carries the same verdict for the S-08 screen to display.
"""

from __future__ import annotations

import pytest

from backend.dataset.import_export import (
    ImportNativeMergeError,
    assert_native_only_merge,
    legacy_import_schema_facts,
    merge_eligibility,
)
from tests.wp3d07 import support


def test_imported_native_merge_raises() -> None:
    """Merging an imported artifact with a native recording raises (`FR-DAT-041`)."""
    native = support.native_facts()
    imported = legacy_import_schema_facts(fps=support.FIXTURE_FPS)
    with pytest.raises(ImportNativeMergeError):
        assert_native_only_merge(native, imported)
    # Order does not matter — the imported side is refused either way.
    with pytest.raises(ImportNativeMergeError):
        assert_native_only_merge(imported, native)


def test_imported_imported_merge_raises() -> None:
    """Even two imported artifacts are refused — the boundary is strict."""
    imported = legacy_import_schema_facts(fps=support.FIXTURE_FPS)
    with pytest.raises(ImportNativeMergeError):
        assert_native_only_merge(imported, imported)


def test_native_native_merge_allowed() -> None:
    """Two schema-identical native recordings are eligible to merge."""
    native = support.native_facts()
    assert_native_only_merge(native, native)
    assert merge_eligibility(native, native).ok


def test_eligibility_is_non_raising_and_explains_refusal() -> None:
    """The eligibility verdict is data (for the GUI), naming the differing axes."""
    native = support.native_facts()
    imported = legacy_import_schema_facts(fps=support.FIXTURE_FPS)
    eligibility = merge_eligibility(native, imported)
    assert not eligibility.ok
    assert "FR-DAT-041" in eligibility.reason
    assert "timestamp.dtype" in eligibility.reason
