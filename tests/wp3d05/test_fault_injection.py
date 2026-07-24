"""Each of the six data-corruption checks bites its defect (`02b` §8.2 WP-3D-05 ①).

The seventh check (the aborted-edit `EDIT_INVALID` marker) has its own file,
`test_edit_marker.py`; this one covers the six on-disk-corruption checks.

For every check, a fresh READY dataset is corrupted in exactly the way that check
exists to catch, and the verdict must flip to INVALID with that check reporting the
failure. This is the acceptance that the verifier is not decorative: a check that
did not fire here would pass a corrupt dataset through to a trainer.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from backend.dataset.integrity import (
    CHECK_DTYPE_MATCH,
    CHECK_INDEX_CONTINUITY,
    CHECK_INFO_CHUNK_CONSISTENCY,
    CHECK_PARQUET_FOOTER,
    CHECK_STATS_HASH_MATCH,
    CHECK_VIDEO_FRAME_COUNT,
    VERDICT_INVALID,
    verify_dataset,
)
from tests.wp3d05 import faults
from tests.wp3d05.materialize import MaterializedDataset

_CASES = [
    (CHECK_PARQUET_FOOTER, faults.inject_footerless_parquet),
    (CHECK_INFO_CHUNK_CONSISTENCY, faults.inject_info_camera_mismatch),
    (CHECK_INDEX_CONTINUITY, faults.inject_index_discontinuity),
    (CHECK_VIDEO_FRAME_COUNT, faults.inject_frame_count_mismatch),
    (CHECK_DTYPE_MATCH, faults.inject_dtype_mismatch),
    (CHECK_STATS_HASH_MATCH, faults.inject_stats_hash_mismatch),
]


@pytest.mark.parametrize("check_name,inject", _CASES, ids=[name for name, _ in _CASES])
def test_injected_defect_makes_dataset_invalid(
    fresh_dataset: Callable[[], MaterializedDataset],
    check_name: str,
    inject: Callable[[MaterializedDataset], None],
) -> None:
    dataset = fresh_dataset()
    inject(dataset)

    report = verify_dataset(dataset.root)

    assert report.verdict == VERDICT_INVALID
    target = report.result(check_name)
    assert target is not None, f"{check_name} did not run"
    assert not target.passed, f"{check_name} did not bite its injected defect"


def test_injected_defect_isolated_to_its_check(
    fresh_dataset: Callable[[], MaterializedDataset],
) -> None:
    """The five non-footer defects fire only their own check, proving check independence.

    A footerless data parquet is excluded here on purpose: it corrupts the file the
    dtype, consistency and continuity checks also read, so those legitimately fire
    too. The other five are surgical.
    """
    for check_name, inject in _CASES:
        if check_name == CHECK_PARQUET_FOOTER:
            continue
        dataset = fresh_dataset()
        inject(dataset)
        report = verify_dataset(dataset.root)
        fired = {result.name for result in report.failures}
        assert fired == {check_name}, f"{check_name} injection also fired {fired - {check_name}}"
