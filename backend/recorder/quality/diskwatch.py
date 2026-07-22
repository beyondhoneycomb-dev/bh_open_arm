"""Disk watch — when free space runs low, safe-store then stop (WP-3B-12, `02b` §5.2).

`02b` §5.2 WP-3B-12 requires the recorder to watch disk space and, when it runs low, to
safe-store and stop rather than write into a full disk and corrupt the dataset. The
episode in flight when the stop fires is soft-stopped: it is NOT auto-saved, and it
carries an `aborted` reason (④). Already-finalised episodes are untouched — that is what
"safe-store" means here: their sidecars and data stay durable while the active episode is
released with a reason.

The watermark is an operational floor, provisional and overridable per `DiskWatch`; it is
not the quality gate `02b` §5.2 WP-3B-12 ⑥ leaves `[결정필요]`.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from backend.recorder.quality.constants import DEFAULT_MIN_FREE_BYTES
from backend.recorder.quality.label import AbortReason, EpisodeLabel
from backend.recorder.quality.sidecar import EpisodeSidecar, write_sidecar
from backend.recorder.quality.store import DatasetStore


class DiskDecision(StrEnum):
    """What the watch tells the recorder to do."""

    CONTINUE = "continue"
    SAFE_STORE_AND_STOP = "safe_store_and_stop"


@dataclass(frozen=True)
class DiskStatus:
    """A point-in-time reading of free space against the watermark.

    Attributes:
        free_bytes: Bytes free on the filesystem holding the dataset.
        total_bytes: Total bytes on that filesystem.
        min_free_bytes: The watermark the reading is compared against.
        below_watermark: Whether free space has fallen to or below the watermark.
    """

    free_bytes: int
    total_bytes: int
    min_free_bytes: int
    below_watermark: bool


@dataclass(frozen=True)
class StopOutcome:
    """The result of a disk-low safe-store-and-stop.

    Attributes:
        decision: Whether the recorder should stop.
        status: The disk reading that drove the decision.
        aborted_label: The soft-stopped episode's label when stopping, else None. It is
            never auto-saved and always carries a reason.
    """

    decision: DiskDecision
    status: DiskStatus
    aborted_label: EpisodeLabel | None


@dataclass(frozen=True)
class DiskWatch:
    """A free-space watch over the filesystem holding a dataset.

    Attributes:
        min_free_bytes: The operational floor below which recording must stop.
    """

    min_free_bytes: int = DEFAULT_MIN_FREE_BYTES

    def check(self, path: Path) -> DiskStatus:
        """Read free space on the filesystem containing `path`.

        Args:
            path: Any path on the target filesystem (typically the dataset root).

        Returns:
            (DiskStatus) The reading, with `below_watermark` set against the floor.
        """
        usage = shutil.disk_usage(path)
        return DiskStatus(
            free_bytes=usage.free,
            total_bytes=usage.total,
            min_free_bytes=self.min_free_bytes,
            below_watermark=usage.free <= self.min_free_bytes,
        )

    def decide(self, store: DatasetStore, active_episode_index: int) -> StopOutcome:
        """Decide whether to safe-store and stop, given the store's disk state.

        When free space is at or below the watermark, the active episode is aborted with
        a `disk-low` reason and its sidecar is written (safe-storing the label without
        auto-saving the episode); the caller stops recording. Otherwise recording
        continues and no label is produced.

        Args:
            store: The dataset store (its root names the filesystem to read).
            active_episode_index: The episode currently being recorded.

        Returns:
            (StopOutcome) The decision, the disk reading, and the aborted label when
                stopping.
        """
        status = self.check(store.root)
        if not status.below_watermark:
            return StopOutcome(decision=DiskDecision.CONTINUE, status=status, aborted_label=None)
        aborted = EpisodeLabel.aborted(active_episode_index, AbortReason.DISK_LOW.value)
        write_sidecar(
            store, EpisodeSidecar(episode_index=active_episode_index, label=aborted, report=None)
        )
        return StopOutcome(
            decision=DiskDecision.SAFE_STORE_AND_STOP, status=status, aborted_label=aborted
        )
