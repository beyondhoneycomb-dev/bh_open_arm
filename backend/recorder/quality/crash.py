"""Crash detection and recovery — a footerless parquet is isolated, then judged (WP-3B-12 ⑤).

`02b` §5.2 WP-3B-12 ⑤: a crash mid-episode leaves a footerless parquet — the Parquet
footer and its trailing `PAR1` magic are written last, so their absence is the signature
of a writer that died before finalising. The band must detect that file, isolate it so it
cannot masquerade as a valid episode, attempt recovery, and then require a *human* to
judge the outcome. It must never auto-save: `recover` produces a PENDING_JUDGMENT label
with `auto_saved` False, and the recovery attempt reports honestly whether it read
anything back rather than fabricating a reconstructed episode.

Detection reads only the trailing magic, so it needs neither pyarrow nor a full parse; the
recovery attempt imports pyarrow lazily to try the deeper read.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from backend.recorder.quality.constants import PARQUET_MAGIC, PARQUET_MAGIC_LEN
from backend.recorder.quality.label import AbortReason, EpisodeLabel
from backend.recorder.quality.sidecar import EpisodeSidecar, write_sidecar
from backend.recorder.quality.store import DatasetStore


@dataclass(frozen=True)
class RecoveryOutcome:
    """The result of attempting to recover an isolated, footerless parquet.

    Attributes:
        recovered: Whether any complete table could be read back. False for a genuinely
            footerless file, where the row-group index the footer holds is gone.
        requires_user_judgment: Always True — a crash artefact is never accepted without
            a person deciding.
        auto_saved: Always False — the recovery path performs no auto-save.
        salvaged_bytes: The size of the isolated file, the bytes that physically survived.
        quarantine_path: Where the file was isolated to.
        reason: The abort reason attached to the pending-judgment label.
    """

    recovered: bool
    requires_user_judgment: bool
    auto_saved: bool
    salvaged_bytes: int
    quarantine_path: str
    reason: str


def is_footerless_parquet(path: Path) -> bool:
    """Report whether a file is a footerless (crash-truncated) parquet.

    A complete Parquet file ends with the four-byte `PAR1` magic that follows the footer.
    A file too short to hold the magic, or one whose last bytes are not the magic, was
    truncated before the footer was written — the crash signature.

    Args:
        path: The candidate parquet file.

    Returns:
        (bool) True when the trailing magic is absent (footerless); False when present.
    """
    if not path.is_file():
        return True
    size = path.stat().st_size
    if size < PARQUET_MAGIC_LEN:
        return True
    with path.open("rb") as handle:
        handle.seek(-PARQUET_MAGIC_LEN, 2)
        trailer = handle.read(PARQUET_MAGIC_LEN)
    return trailer != PARQUET_MAGIC


def isolate(path: Path, store: DatasetStore) -> Path:
    """Move a crash-detected file into the store's quarantine directory.

    Isolation is what stops a footerless file from being read as a valid episode: it
    leaves the dataset's data tree so no consumer joins it in.

    Args:
        path: The footerless file.
        store: The dataset store whose quarantine directory receives it.

    Returns:
        (Path) The file's new path inside quarantine.
    """
    destination = store.ensure_quarantine_dir() / path.name
    shutil.move(str(path), str(destination))
    return destination


def attempt_recovery(quarantined_path: Path) -> bool:
    """Attempt to read a table back from an isolated file, reporting honestly.

    A truly footerless parquet cannot be read: pyarrow needs the footer's row-group index,
    which the crash truncated. This returns True only if a table genuinely reads back —
    it never claims a recovery it did not make.

    Args:
        quarantined_path: The isolated file.

    Returns:
        (bool) True when a table was read, False otherwise.
    """
    try:
        import pyarrow.parquet as pq
    except ImportError:
        return False
    # pyarrow's ArrowInvalid subclasses ValueError; a truncated footer raises it, and a
    # missing/short file raises OSError. Both mean "no table read", never a crash here.
    try:
        pq.read_table(quarantined_path)
    except (OSError, ValueError):
        return False
    return True


def recover(
    store: DatasetStore, path: Path, episode_index: int
) -> tuple[RecoveryOutcome, EpisodeLabel]:
    """Isolate a footerless parquet, attempt recovery, and hold it for human judgment.

    The full ⑤ path: the file is moved to quarantine, a recovery read is attempted, and a
    PENDING_JUDGMENT label is written for the episode. The label is never auto-saved — a
    person must render the verdict (`with_manual`) or discard it with a reason.

    Args:
        store: The dataset store layout.
        path: The footerless parquet, still in the data tree.
        episode_index: The episode the file belonged to.

    Returns:
        (tuple[RecoveryOutcome, EpisodeLabel]) The recovery outcome and the pending label,
            the label also written to the store as a sidecar.
    """
    quarantined = isolate(path, store)
    recovered = attempt_recovery(quarantined)
    reason = AbortReason.CRASH_FOOTERLESS_PARQUET.value
    outcome = RecoveryOutcome(
        recovered=recovered,
        requires_user_judgment=True,
        auto_saved=False,
        salvaged_bytes=quarantined.stat().st_size,
        quarantine_path=str(quarantined),
        reason=reason,
    )
    label = EpisodeLabel.pending_judgment(episode_index, reason)
    write_sidecar(store, EpisodeSidecar(episode_index=episode_index, label=label, report=None))
    return outcome, label
