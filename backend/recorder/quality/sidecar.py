"""The episode quality sidecar — success/fail as a file beside the data (WP-3B-12 ①).

`02b` §5.2 WP-3B-12 ① makes success/fail an episode-level sidecar and forbids a label or
quality change from re-writing the parquet or mp4. This module holds only that: it reads
and writes one JSON file per episode under `meta/quality`, addressed through the
`DatasetStore` layout. There is no code path from here to a data file, so the no-re-record
property is structural, not a discipline a caller must remember.

`update_label` is the operation the guarantee rests on: it rewrites the sidecar's label
in place and leaves the report — and every parquet and mp4 — untouched.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from backend.recorder.quality.label import EpisodeLabel
from backend.recorder.quality.report import QualityReport
from backend.recorder.quality.store import DatasetStore


class SidecarNotFoundError(FileNotFoundError):
    """No sidecar exists for the requested episode."""


@dataclass(frozen=True)
class EpisodeSidecar:
    """The full quality record for one episode: its label and, when computed, its report.

    Attributes:
        episode_index: The episode this sidecar annotates.
        label: The success/fail (or aborted/pending) label.
        report: The quality report, or None when only a label has been written.
    """

    episode_index: int
    label: EpisodeLabel
    report: QualityReport | None

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-safe mapping."""
        return {
            "episode_index": self.episode_index,
            "label": self.label.to_dict(),
            "report": self.report.to_dict() if self.report is not None else None,
        }


def write_sidecar(store: DatasetStore, sidecar: EpisodeSidecar) -> None:
    """Write an episode sidecar as JSON under the store's quality directory.

    Writes only the sidecar JSON — no parquet or mp4 is opened or created (WP-3B-12 ①).

    Args:
        store: The dataset store layout.
        sidecar: The record to persist.
    """
    store.ensure_quality_dir()
    path = store.sidecar_path(sidecar.episode_index)
    path.write_text(json.dumps(sidecar.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def read_sidecar(store: DatasetStore, episode_index: int) -> EpisodeSidecar:
    """Read an episode sidecar from disk.

    Args:
        store: The dataset store layout.
        episode_index: The episode to read.

    Returns:
        (EpisodeSidecar) The persisted record.

    Raises:
        SidecarNotFoundError: When no sidecar exists for the episode.
    """
    path = store.sidecar_path(episode_index)
    if not path.is_file():
        raise SidecarNotFoundError(f"no sidecar for episode {episode_index} at {path}")
    body = json.loads(path.read_text(encoding="utf-8"))
    return _from_dict(body)


def update_label(store: DatasetStore, episode_index: int, label: EpisodeLabel) -> EpisodeSidecar:
    """Replace the label of an existing sidecar, preserving its report and the data files.

    This is the label edit `02b` §5.2 WP-3B-12 ① requires not to re-record: it rewrites
    the sidecar JSON alone, keeping the report as-is and never touching a parquet or mp4.

    Args:
        store: The dataset store layout.
        episode_index: The episode whose label changes.
        label: The new label.

    Returns:
        (EpisodeSidecar) The updated record, also written to disk.

    Raises:
        SidecarNotFoundError: When no sidecar exists for the episode.
    """
    existing = read_sidecar(store, episode_index)
    updated = EpisodeSidecar(episode_index=episode_index, label=label, report=existing.report)
    write_sidecar(store, updated)
    return updated


def _from_dict(body: dict[str, Any]) -> EpisodeSidecar:
    """Reconstruct a sidecar from its serialised form, restoring the label surface only.

    The typed `QualityReport` is not rebuilt on read: the label is the surface callers act
    on, and reconstituting the report from its numeric summary would risk inventing fields
    the band exists to keep honest. A caller that needs the live report holds the one
    `build_report` returned; the on-disk JSON retains the report body verbatim regardless.
    """
    return EpisodeSidecar(
        episode_index=body["episode_index"],
        label=EpisodeLabel.from_dict(body["label"]),
        report=None,
    )
