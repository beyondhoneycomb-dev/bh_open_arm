"""Unit coverage for the sequential-read bandwidth and bound helpers.

These are the pieces the throughput acceptance is built from; the fio proxy
(`measure_sequential_read_bandwidth`) and the bound arithmetic are pinned here so a
change to either surfaces on its own rather than only through the timing test.
"""

from __future__ import annotations

import math

from backend.dataset.integrity import (
    dataset_byte_size,
    measure_sequential_read_bandwidth,
    regression_bound_seconds,
    sequential_read_seconds,
    within_regression_bound,
)
from tests.wp3d05.materialize import MaterializedDataset


def test_dataset_byte_size_counts_every_file(materialized: MaterializedDataset) -> None:
    total = dataset_byte_size(materialized.root)
    walked = sum(p.stat().st_size for p in materialized.root.rglob("*") if p.is_file())
    assert total == walked > 0


def test_measure_bandwidth_is_positive(materialized: MaterializedDataset) -> None:
    bandwidth = measure_sequential_read_bandwidth(materialized.root)
    assert bandwidth > 0.0


def test_bound_is_twice_the_read_time() -> None:
    dataset_bytes = 100 * 1024 * 1024
    bandwidth = 50 * 1024 * 1024
    assert sequential_read_seconds(dataset_bytes, bandwidth) == 2.0
    assert regression_bound_seconds(dataset_bytes, bandwidth) == 4.0


def test_within_bound_is_inclusive_at_the_edge() -> None:
    dataset_bytes = 10 * 1024 * 1024
    bandwidth = 10 * 1024 * 1024
    bound = regression_bound_seconds(dataset_bytes, bandwidth)
    assert within_regression_bound(bound, dataset_bytes, bandwidth)
    assert not within_regression_bound(bound + 1e-6, dataset_bytes, bandwidth)


def test_infinite_bandwidth_collapses_the_bound() -> None:
    assert sequential_read_seconds(1234, math.inf) == 0.0
    assert regression_bound_seconds(1234, math.inf) == 0.0
