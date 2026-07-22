"""WP-3B-12 — disk watch safe-stores then stops; the soft-stopped episode is not auto-saved.

`02b` §5.2 WP-3B-12: watch disk space and, when it runs low, safe-store then stop. The
in-flight episode is soft-stopped — aborted with a reason, never auto-saved (④) — while
already-finalised episodes stay durable (that is what safe-store means).
"""

from __future__ import annotations

from pathlib import Path

from backend.recorder.quality.diskwatch import DiskDecision, DiskWatch
from backend.recorder.quality.label import AbortReason, EpisodeLabel, EpisodeStatus, Verdict
from backend.recorder.quality.sidecar import EpisodeSidecar, read_sidecar, write_sidecar
from backend.recorder.quality.store import DatasetStore

# A watermark far above any real free space forces the low-disk branch deterministically,
# without needing to fill the test filesystem.
_UNREACHABLE_WATERMARK_BYTES = 1 << 62


def test_ample_disk_continues(tmp_path: Path) -> None:
    """With the watermark at zero, a real filesystem is above it and recording continues."""
    outcome = DiskWatch(min_free_bytes=0).decide(
        DatasetStore(root=tmp_path), active_episode_index=4
    )

    assert outcome.decision is DiskDecision.CONTINUE
    assert outcome.aborted_label is None
    assert outcome.status.below_watermark is False


def test_low_disk_safe_stores_and_stops(tmp_path: Path) -> None:
    """④ Below the watermark the active episode is aborted with a reason and not auto-saved."""
    store = DatasetStore(root=tmp_path)

    outcome = DiskWatch(min_free_bytes=_UNREACHABLE_WATERMARK_BYTES).decide(
        store, active_episode_index=7
    )

    assert outcome.decision is DiskDecision.SAFE_STORE_AND_STOP
    label = outcome.aborted_label
    assert label is not None
    assert label.status is EpisodeStatus.ABORTED
    assert label.abort_reason == AbortReason.DISK_LOW.value
    assert label.auto_saved is False
    # The abort is safe-stored: its sidecar is written so the stop leaves a reasoned record.
    assert read_sidecar(store, 7).label.status is EpisodeStatus.ABORTED


def test_safe_store_leaves_finalised_episodes_untouched(tmp_path: Path) -> None:
    """A disk-low stop on the active episode does not disturb an already-finalised one."""
    store = DatasetStore(root=tmp_path)
    finalised = EpisodeLabel.suggested(0, Verdict.SUCCESS).with_manual(Verdict.SUCCESS)
    write_sidecar(store, EpisodeSidecar(0, finalised, None))

    DiskWatch(min_free_bytes=_UNREACHABLE_WATERMARK_BYTES).decide(store, active_episode_index=1)

    kept = read_sidecar(store, 0).label
    assert kept.status is EpisodeStatus.JUDGED
    assert kept.auto_saved is True
    assert kept.effective_verdict() is Verdict.SUCCESS
