"""Run the seven integrity checks and render the READY/INVALID verdict (WP-3D-05).

`verify_dataset` reads the dataset once, runs every required check, times the run,
and returns an `IntegrityReport`. `ensure_training_ready` is the boundary a
training loader and the WP-3C-06 source-delete interlock call: it verifies and
raises unless the dataset is READY, so an INVALID dataset can never be exposed as a
training input (`FR-DAT-051`, `NFR-DAT-005`).

Every check runs even when an earlier one failed — the report is a full picture of
what is wrong, not the first thing — and no check is allowed to crash the run: an
unexpected exception becomes a FAIL for that check, because a verifier that dies on
a corrupt dataset leaves it un-judged rather than INVALID.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from backend.dataset.integrity.bandwidth import dataset_byte_size
from backend.dataset.integrity.checks import ALL_CHECKS
from backend.dataset.integrity.dataset import DatasetInventory
from backend.dataset.integrity.report import (
    CheckResult,
    CheckStatus,
    IntegrityReport,
    failed,
)

Check = Callable[[DatasetInventory], CheckResult]


def _run_check(check: Check, inventory: DatasetInventory) -> CheckResult:
    """Run one check, turning any unexpected exception into a FAIL result."""
    try:
        return check(inventory)
    except Exception as bad:  # noqa: BLE001 — a check must never crash the verifier
        name = getattr(check, "__name__", "check").removeprefix("check_")
        return failed(name, f"unexpected error: {bad}")


def verify_dataset(
    root: Path,
    recorded_stats_hash: str | None = None,
    checks: tuple[Check, ...] = ALL_CHECKS,
) -> IntegrityReport:
    """Verify a dataset directory and return its integrity report.

    Args:
        root: The dataset root directory.
        recorded_stats_hash: An explicit stats hash to check against; when None the
            stats-hash check falls back to the value recorded in `info.json`.
        checks: The checks to run; defaults to the full required set. Narrowing this
            set produces an INVALID verdict, since the report requires the whole set.

    Returns:
        (IntegrityReport) The per-check results, timing, and READY/INVALID verdict.
    """
    root = Path(root)
    inventory = DatasetInventory.open(root, recorded_stats_hash)

    start = time.perf_counter()
    results = tuple(_run_check(check, inventory) for check in checks)
    elapsed = time.perf_counter() - start

    return IntegrityReport(
        root=root,
        results=results,
        elapsed_seconds=elapsed,
        dataset_bytes=dataset_byte_size(root),
    )


def is_ready(root: Path, recorded_stats_hash: str | None = None) -> bool:
    """Return whether a dataset verifies READY (all required checks pass)."""
    return verify_dataset(root, recorded_stats_hash).ready


def ensure_training_ready(root: Path, recorded_stats_hash: str | None = None) -> IntegrityReport:
    """Verify a dataset and raise unless it is READY — the training-input gate.

    This is the interlock WP-3C-06 (source-delete) consumes: a dataset that cannot
    certify READY is never handed to a trainer and never has its source deleted.

    Args:
        root: The dataset root directory.
        recorded_stats_hash: An explicit stats hash to check against.

    Returns:
        (IntegrityReport) The report, only when the dataset is READY.

    Raises:
        IntegrityError: When the dataset is INVALID (any check missing or failed).
    """
    report = verify_dataset(root, recorded_stats_hash)
    report.raise_if_invalid()
    return report


__all__ = [
    "CheckResult",
    "CheckStatus",
    "IntegrityReport",
    "ensure_training_ready",
    "is_ready",
    "verify_dataset",
]
