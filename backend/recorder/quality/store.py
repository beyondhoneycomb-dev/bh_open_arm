"""The dataset store layout — the single authority on where quality artefacts live (WP-3B-12).

`02b` §5.2 WP-3B-12 calls this band "라벨 · 품질 리포트 · 저장소". This module is the
저장소 (store) layer's layout: given a recorded dataset's root directory, it names where
the per-episode quality sidecar goes and where a crash-quarantined file is isolated. It
owns those paths so that `sidecar`, `diskwatch` and `crash` all resolve one location and
none re-derives the convention.

It touches only the `meta/quality` and `meta/quarantine` subtrees. The recorded parquet
and mp4 are never addressed here, which is how the "label edits do not re-record" rule
(①) holds structurally: there is no path from a label write to a data file.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.recorder.quality.constants import (
    QUALITY_SUBDIR,
    QUARANTINE_SUBDIR,
    SIDECAR_PREFIX,
    SIDECAR_SUFFIX,
)


@dataclass(frozen=True)
class DatasetStore:
    """The on-disk layout of one recorded dataset's quality artefacts.

    Attributes:
        root: The dataset's root directory, the same directory the recorder writes
            `meta/`, `data/` and `videos/` under.
    """

    root: Path

    def quality_dir(self) -> Path:
        """The directory the per-episode quality sidecars live in."""
        return self.root / QUALITY_SUBDIR

    def quarantine_dir(self) -> Path:
        """The directory crash-detected, footerless files are isolated into."""
        return self.root / QUARANTINE_SUBDIR

    def sidecar_path(self, episode_index: int) -> Path:
        """The sidecar path for one episode.

        Args:
            episode_index: The episode index.

        Returns:
            (Path) `<root>/meta/quality/episode_<index>.json`.
        """
        return self.quality_dir() / f"{SIDECAR_PREFIX}{episode_index}{SIDECAR_SUFFIX}"

    def ensure_quality_dir(self) -> Path:
        """Create the quality directory if absent and return it."""
        directory = self.quality_dir()
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def ensure_quarantine_dir(self) -> Path:
        """Create the quarantine directory if absent and return it."""
        directory = self.quarantine_dir()
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def episode_indices(self) -> tuple[int, ...]:
        """The episode indices that have a sidecar on disk, ascending.

        Returns:
            (tuple[int, ...]) Indices parsed from the sidecar filenames; empty when the
                quality directory does not yet exist.
        """
        directory = self.quality_dir()
        if not directory.is_dir():
            return ()
        indices: list[int] = []
        for path in directory.glob(f"{SIDECAR_PREFIX}*{SIDECAR_SUFFIX}"):
            stem = path.name[len(SIDECAR_PREFIX) : -len(SIDECAR_SUFFIX)]
            if stem.isdigit():
                indices.append(int(stem))
        return tuple(sorted(indices))
