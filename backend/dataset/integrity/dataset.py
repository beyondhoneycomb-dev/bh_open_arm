"""Read a dataset directory once, for the seven integrity checks to share.

The verifier reuses the WP-3D-01 viewer's `DatasetLayout` to parse `meta/info.json`
and the packed episode metadata — the same LeRobot v3.0 storage convention, read
as data (`06` §5.6), never reimplemented here. This module adds only what a
verifier needs beyond a viewer: it discovers every parquet file on disk (so a
footerless one is found even when it breaks layout construction), separates the
image feature keys from the columns that live in the data parquet, and locates the
stats sidecar and the dataset's recorded stats hash.

Layout construction can fail (a missing/corrupt `info.json`, an unreadable episode
-metadata parquet). That is itself an integrity fault, so the inventory captures
the error rather than raising, and the checks that need the layout fail cleanly
while the footer check — which globs the raw tree — still runs.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.dataset.integrity.constants import (
    INFO_STATS_HASH_KEY,
    PARQUET_SUFFIX,
    STATS_RELATIVE_PATH,
)
from backend.dataset.viewer.layout import DatasetLayout, DatasetLayoutError


class InventoryError(ValueError):
    """Raised by an inventory accessor that needs a layout the dataset denied."""


def _scalar(value: Any) -> Any:
    """Collapse a one-element-list metadata cell to its scalar.

    Episode-metadata columns are written as a one-element list per row; index
    columns are plain scalars. This mirrors the viewer layout's own cell reading
    (the layout keeps that helper private) so the verifier reads the same values.
    """
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return value[0] if value else None
    return value


@dataclass
class DatasetInventory:
    """A dataset directory read once and shared across the integrity checks.

    Attributes:
        root: The dataset root.
        layout: The parsed v3.0 layout, or None when it could not be built.
        layout_error: The reason the layout could not be built, or None.
        recorded_stats_hash: The stats hash to check the stats table against — the
            caller's override, else the value stamped in `info.json`.
    """

    root: Path
    layout: DatasetLayout | None
    layout_error: str | None
    recorded_stats_hash: str | None

    @classmethod
    def open(cls, root: Path, recorded_stats_hash: str | None = None) -> DatasetInventory:
        """Read a dataset directory, capturing any layout error rather than raising.

        Args:
            root: The dataset root directory.
            recorded_stats_hash: An explicit stats hash to verify against; when
                None the check falls back to `info.json`'s recorded value.

        Returns:
            (DatasetInventory) The shared read of the dataset.
        """
        root = Path(root)
        layout: DatasetLayout | None
        error: str | None
        try:
            layout = DatasetLayout(root)
            error = None
        except DatasetLayoutError as bad:
            layout = None
            error = str(bad)
        if recorded_stats_hash is None and layout is not None:
            recorded = layout.info.get(INFO_STATS_HASH_KEY)
            recorded_stats_hash = str(recorded) if recorded is not None else None
        return cls(
            root=root,
            layout=layout,
            layout_error=error,
            recorded_stats_hash=recorded_stats_hash,
        )

    def require_layout(self) -> DatasetLayout:
        """Return the layout, or raise `InventoryError` with why it is unavailable.

        Raises:
            InventoryError: When the layout could not be built from the dataset.
        """
        if self.layout is None:
            raise InventoryError(self.layout_error or "dataset layout could not be read")
        return self.layout

    def parquet_files(self) -> tuple[Path, ...]:
        """Every parquet file under the root, found by globbing the raw tree.

        Globbing rather than resolving templates is deliberate: a footerless file
        must be found even when it is the very file that breaks layout parsing.
        """
        return tuple(sorted(self.root.rglob(f"*{PARQUET_SUFFIX}")))

    def image_feature_keys(self) -> frozenset[str]:
        """The `observation.images.*` keys, taken from the layout's camera streams.

        Reusing `camera_streams` keeps the image/non-image split on the same
        `info.json` reading the viewer uses, rather than re-deriving the prefix.
        """
        layout = self.require_layout()
        return frozenset(stream.image_key for stream in layout.camera_streams())

    def stored_feature_keys(self) -> frozenset[str]:
        """The feature keys that live as columns in the data parquet.

        Image features are stored as mp4/tiff, not parquet columns, so they are
        excluded; what remains (`observation.state`, `action`, the five meta
        features) is exactly the set the data-parquet schema must carry.
        """
        layout = self.require_layout()
        images = self.image_feature_keys()
        return frozenset(key for key in layout.features if key not in images)

    def data_files(self) -> tuple[Path, ...]:
        """The distinct data parquet files the episode metadata resolves to."""
        layout = self.require_layout()
        files: list[Path] = []
        for episode_index in layout.episode_indices() or (0,):
            location = layout.locate(episode_index)
            if location.data_file not in files:
                files.append(location.data_file)
        return tuple(files)

    def episode_rows(self) -> tuple[dict[str, Any], ...]:
        """Episode-metadata rows, ascending by index, list-cells collapsed.

        Returns:
            (tuple[dict[str, Any]]) One row per episode with scalar cells; empty
                when the dataset declares no episode metadata.
        """
        layout = self.require_layout()
        rows: list[dict[str, Any]] = []
        for episode_index in layout.episode_indices():
            row = layout.episodes[episode_index]
            rows.append({key: _scalar(value) for key, value in row.items()})
        return tuple(rows)

    def stats_path(self) -> Path:
        """The stats sidecar path (`meta/stats.json`)."""
        return self.root / STATS_RELATIVE_PATH

    def load_stats_table(self) -> dict[str, dict[str, list[float]]]:
        """Read the stats sidecar as a feature -> metric -> array table.

        Returns:
            (dict) The parsed stats table.

        Raises:
            InventoryError: When the sidecar is missing or not valid JSON.
        """
        path = self.stats_path()
        if not path.is_file():
            raise InventoryError(f"{path} is missing; the dataset carries no stats sidecar")
        try:
            table = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as bad:
            raise InventoryError(f"{path} is not valid JSON: {bad}") from bad
        if not isinstance(table, dict):
            raise InventoryError(f"{path} is not a feature -> metric stats table")
        return table
