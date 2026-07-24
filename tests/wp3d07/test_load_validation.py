"""WP-3D-07 ④: an imported artifact fails load validation => INVALID.

`FR-DAT-043`: an import must load once and its `timestamp` gaps must fall within
`1/fps ± tolerance_s` (default `1e-4`); otherwise it is INVALID and never a training
input. This module checks the good synthetic grid is VALID, a jittered grid is INVALID,
the degenerate short grid is INVALID, and that `accept_imported_dataset` propagates
INVALID to the outcome the batch `INTEGRITY READY` invariant depends on.
"""

from __future__ import annotations

import pytest

from backend.dataset.import_export import (
    TIMESTAMP_INTERVAL_TOLERANCE_S,
    Validity,
    accept_imported_dataset,
    validate_import_load,
)
from tests.wp3d07 import support


def test_good_grid_is_valid() -> None:
    """The synthetic dataset's `frame_index / fps` grid validates VALID."""
    result = validate_import_load(support.fixture_timestamps(), support.FIXTURE_FPS)
    assert result.validity is Validity.VALID
    assert result.worst_interval_error <= TIMESTAMP_INTERVAL_TOLERANCE_S


def test_jittered_grid_is_invalid() -> None:
    """A gap pushed outside `1/fps ± 1e-4` yields INVALID (`FR-DAT-043`)."""
    result = validate_import_load(support.jittered_timestamps(), support.FIXTURE_FPS)
    assert result.validity is Validity.INVALID
    assert result.worst_interval_error > TIMESTAMP_INTERVAL_TOLERANCE_S


def test_single_frame_grid_is_invalid() -> None:
    """A grid with no interval to check cannot be certified — INVALID."""
    result = validate_import_load([0.0], support.FIXTURE_FPS)
    assert result.validity is Validity.INVALID


def test_nonpositive_fps_raises() -> None:
    """A non-positive fps has no defined expected interval — a caller error."""
    with pytest.raises(ValueError, match="fps must be positive"):
        validate_import_load(support.fixture_timestamps(), 0)


def test_accept_propagates_invalid() -> None:
    """A broken import surfaces INVALID on the accepted outcome, not a silent pass."""
    outcome = accept_imported_dataset(support.broken_imported_dataset(), support.native_facts())
    assert outcome.validity is Validity.INVALID
    assert outcome.load.validity is Validity.INVALID


def test_accept_rejects_a_native_tagged_artifact() -> None:
    """Accepting a native-tagged artifact through the import path is a caller error."""
    from backend.dataset.import_export import ImportedDataset

    native_tagged = ImportedDataset(
        schema=support.native_facts(), timestamps=support.fixture_timestamps()
    )
    with pytest.raises(ValueError, match="IMPORTED_LEGACY"):
        accept_imported_dataset(native_tagged, support.native_facts())
