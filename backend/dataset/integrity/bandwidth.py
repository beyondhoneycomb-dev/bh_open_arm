"""The sequential-read regression bound for verification time (`02b` §8.2 WP-3D-05 ③).

Verification must not take longer than twice the time to read the dataset once,
sequentially. The reference bandwidth is measured with fio on the target; on a
machine without that measurement `measure_sequential_read_bandwidth` is the proxy
— it reads the dataset's own bytes back sequentially and reports the achieved rate.

The bound is a guard against an algorithmic regression (re-reading files, decoding
full pixels where a header would do, an accidental O(n^2)); it is not a wall-clock
SLA. So the numerator is the dataset's byte size and the denominator is a read
bandwidth, and both must be measured over the same files for the ratio to mean
anything.
"""

from __future__ import annotations

import time
from pathlib import Path

from backend.dataset.integrity.constants import (
    SEQUENTIAL_READ_BLOCK_BYTES,
    SEQUENTIAL_READ_REGRESSION_MULTIPLIER,
)


def dataset_byte_size(root: Path) -> int:
    """Return the total on-disk size of every file under a dataset root.

    Args:
        root: The dataset root directory.

    Returns:
        (int) Sum of file sizes in bytes.
    """
    total = 0
    for path in Path(root).rglob("*"):
        if path.is_file():
            total += path.stat().st_size
    return total


def measure_sequential_read_bandwidth(
    root: Path, block_bytes: int = SEQUENTIAL_READ_BLOCK_BYTES
) -> float:
    """Measure the achieved sequential read bandwidth over a dataset's files.

    Reads every file end to end in `block_bytes` chunks and divides the bytes read
    by the elapsed time. This is the in-repo stand-in for a fio measurement; on a
    warm cache it reports memory bandwidth, on cold storage it reports the disk.

    Args:
        root: The dataset root directory.
        block_bytes: The read chunk size.

    Returns:
        (float) Bytes per second; `inf` when there is nothing to read or the read
            was too fast to time.
    """
    total = 0
    start = time.perf_counter()
    for path in sorted(Path(root).rglob("*")):
        if not path.is_file():
            continue
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(block_bytes)
                if not chunk:
                    break
                total += len(chunk)
    elapsed = time.perf_counter() - start
    if total == 0 or elapsed <= 0.0:
        return float("inf")
    return total / elapsed


def sequential_read_seconds(dataset_bytes: int, bandwidth_bytes_per_s: float) -> float:
    """Return the time to read `dataset_bytes` once at a given bandwidth."""
    if bandwidth_bytes_per_s <= 0.0 or bandwidth_bytes_per_s == float("inf"):
        return 0.0
    return dataset_bytes / bandwidth_bytes_per_s


def regression_bound_seconds(dataset_bytes: int, bandwidth_bytes_per_s: float) -> float:
    """Return the maximum verification time before it counts as a regression.

    Args:
        dataset_bytes: The dataset's on-disk size.
        bandwidth_bytes_per_s: The sequential read bandwidth (fio, or the proxy).

    Returns:
        (float) `multiplier * (bytes / bandwidth)` seconds.
    """
    return SEQUENTIAL_READ_REGRESSION_MULTIPLIER * sequential_read_seconds(
        dataset_bytes, bandwidth_bytes_per_s
    )


def within_regression_bound(
    elapsed_seconds: float, dataset_bytes: int, bandwidth_bytes_per_s: float
) -> bool:
    """Whether a verification time is within the 2x sequential-read bound.

    Args:
        elapsed_seconds: The measured verification time.
        dataset_bytes: The dataset's on-disk size.
        bandwidth_bytes_per_s: The sequential read bandwidth reference.

    Returns:
        (bool) True when `elapsed <= 2 * (bytes / bandwidth)`.
    """
    return elapsed_seconds <= regression_bound_seconds(dataset_bytes, bandwidth_bytes_per_s)
