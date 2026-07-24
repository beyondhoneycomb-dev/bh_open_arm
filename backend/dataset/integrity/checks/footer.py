"""Check 1 — every parquet file carries a readable footer (`02b` §8.2 WP-3D-05).

A parquet writer appends the schema/row-group metadata (the footer) and the
closing `PAR1` magic last, so a process killed mid-write leaves a file whose data
pages are present but whose footer is truncated. Such a file opens without error
in a plain byte read and only fails when something tries to parse it — exactly the
silent corruption a training loader must never ingest.

The check bites twice: the trailing magic must be present (the cheap signature),
and pyarrow must parse the footer (the real read). A footerless file fails one or
both.
"""

from __future__ import annotations

import pyarrow.parquet as pq

from backend.dataset.integrity.constants import (
    CHECK_PARQUET_FOOTER,
    PARQUET_MAGIC,
    PARQUET_MAGIC_LEN,
)
from backend.dataset.integrity.dataset import DatasetInventory
from backend.dataset.integrity.report import CheckResult, failed, passed


def _footer_defect(path_bytes: bytes, parse_error: str | None) -> str | None:
    """Return why a parquet file's footer is unreadable, or None when it is fine."""
    if len(path_bytes) < PARQUET_MAGIC_LEN or path_bytes[-PARQUET_MAGIC_LEN:] != PARQUET_MAGIC:
        return "trailing PAR1 magic absent (file truncated before its footer)"
    if parse_error is not None:
        return f"footer parse failed ({parse_error})"
    return None


def check_parquet_footer(inventory: DatasetInventory) -> CheckResult:
    """Verify every parquet file under the dataset root has a readable footer.

    Args:
        inventory: The shared dataset read.

    Returns:
        (CheckResult) PASS when all parquet files parse; FAIL naming the first
            file whose footer is truncated or unparseable.
    """
    files = inventory.parquet_files()
    if not files:
        return failed(CHECK_PARQUET_FOOTER, "no parquet files found under the dataset root")

    for path in files:
        tail = b""
        try:
            with path.open("rb") as handle:
                if path.stat().st_size >= PARQUET_MAGIC_LEN:
                    handle.seek(-PARQUET_MAGIC_LEN, 2)
                    tail = handle.read(PARQUET_MAGIC_LEN)
        except OSError as bad:
            return failed(CHECK_PARQUET_FOOTER, f"{path}: cannot read file ({bad})")

        parse_error: str | None = None
        try:
            pq.read_metadata(path)
        except Exception as bad:  # noqa: BLE001 — any pyarrow failure is a footer/corruption signal
            parse_error = str(bad)

        defect = _footer_defect(tail, parse_error)
        if defect is not None:
            return failed(CHECK_PARQUET_FOOTER, f"{path}: {defect}")

    return passed(CHECK_PARQUET_FOOTER, f"{len(files)} parquet file(s) have readable footers")
