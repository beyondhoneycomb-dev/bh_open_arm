"""Read the raw capture source — the pre-conversion output the interlock protects.

The raw source is what the capture band (`WP-3C-02`) produces before conversion to
the LeRobot v3.0 layout: one directory per episode, each holding a manifest (the
original frame count and fps) and the CTR-CAP@v1 capture-timestamp sidecar as flat
records. This band consumes those files as *data* — it guards the capture output,
it does not import the capture code (`WP-3C-02` is a hardware WP with no code edge,
`06` §5.6). The manifest and sidecar together are the ground truth every
capture-preservation check is measured against.

A raw source that cannot be read is itself a reason to refuse deletion: the
inability to establish the original frame count or capture instants means the
conversion cannot be certified to have preserved them, so the accessors raise
rather than fabricate a value a delete would then be granted against.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.capture_interlock.constants import (
    MANIFEST_FPS_KEY,
    MANIFEST_LENGTH_KEY,
    RAW_CAPTURE_TS_FILENAME,
    RAW_EPISODE_DIR_TEMPLATE,
    RAW_MANIFEST_FILENAME,
)
from contracts.capture.schema import CaptureSidecar, sidecar_from_records


class CaptureSourceError(ValueError):
    """Raised when the raw capture source cannot be read as the ground truth.

    A missing manifest, an unreadable capture_ts sidecar, or a non-positive fps or
    length all raise: without a trustworthy original frame count and capture-instant
    stream there is nothing to certify the conversion against, and a delete must be
    refused rather than granted against a guessed value.
    """


@dataclass(frozen=True)
class CaptureSourceEpisode:
    """One episode of the raw capture source: its size and capture instants.

    Attributes:
        episode_index: The episode this record describes.
        fps: The capture rate the episode was recorded at.
        length: The original grabbed frame count N — the number every
            frame/row/video-length preservation check is anchored to.
        sidecar: The CTR-CAP@v1 capture-timestamp sidecar for the episode.
    """

    episode_index: int
    fps: int
    length: int
    sidecar: CaptureSidecar

    @property
    def duration_seconds(self) -> float:
        """The episode's temporal length in seconds — `length / fps`."""
        return self.length / self.fps


class CaptureSource:
    """The raw capture source on disk, read per episode for the interlock.

    Ownership: this object holds no file handles; it discovers the per-episode
    directories at construction and reads each episode's manifest and sidecar on
    demand. `delete` is the one mutating operation, and it removes the whole source
    tree — the interlock calls it only behind a `DELETABLE` decision.
    """

    def __init__(self, root: Path) -> None:
        """Discover the raw source's per-episode directories under a root.

        Args:
            root: The raw capture source root directory.
        """
        self.root = Path(root)

    def exists(self) -> bool:
        """Whether the raw source root is still present on disk."""
        return self.root.is_dir()

    def _episode_dir(self, episode_index: int) -> Path:
        """The directory holding one episode's raw capture files."""
        return self.root / RAW_EPISODE_DIR_TEMPLATE.format(episode_index=episode_index)

    def episode_indices(self) -> tuple[int, ...]:
        """The episode indices present in the raw source, ascending.

        Returns:
            (tuple[int, ...]) The discovered episode indices; empty when the source
                directory is absent or holds no episode directories.
        """
        if not self.root.is_dir():
            return ()
        indices: list[int] = []
        prefix = RAW_EPISODE_DIR_TEMPLATE.split("{", 1)[0]
        for child in self.root.iterdir():
            if not child.is_dir() or not child.name.startswith(prefix):
                continue
            suffix = child.name[len(prefix) :]
            if suffix.isdigit():
                indices.append(int(suffix))
        return tuple(sorted(indices))

    def episode(self, episode_index: int) -> CaptureSourceEpisode:
        """Read one episode's manifest and capture-timestamp sidecar.

        Args:
            episode_index: The episode to read.

        Returns:
            (CaptureSourceEpisode) The episode's fps, original frame count and sidecar.

        Raises:
            CaptureSourceError: When the manifest or sidecar is missing/unreadable,
                or declares a non-positive fps or length.
        """
        episode_dir = self._episode_dir(episode_index)
        manifest = self._read_manifest(episode_dir)
        fps = int(manifest.get(MANIFEST_FPS_KEY, 0))
        length = int(manifest.get(MANIFEST_LENGTH_KEY, 0))
        if fps <= 0:
            raise CaptureSourceError(
                f"raw episode {episode_index} declares a non-positive fps {fps!r}"
            )
        if length <= 0:
            raise CaptureSourceError(
                f"raw episode {episode_index} declares a non-positive length {length!r}"
            )
        sidecar = self._read_sidecar(episode_dir, episode_index)
        return CaptureSourceEpisode(
            episode_index=episode_index, fps=fps, length=length, sidecar=sidecar
        )

    def _read_manifest(self, episode_dir: Path) -> dict[str, Any]:
        """Read an episode's raw manifest JSON."""
        path = episode_dir / RAW_MANIFEST_FILENAME
        if not path.is_file():
            raise CaptureSourceError(f"raw manifest {path} is missing")
        try:
            body = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as bad:
            raise CaptureSourceError(f"raw manifest {path} is not valid JSON: {bad}") from bad
        if not isinstance(body, dict):
            raise CaptureSourceError(f"raw manifest {path} is not a JSON object")
        return body

    def _read_sidecar(self, episode_dir: Path, episode_index: int) -> CaptureSidecar:
        """Read and validate an episode's CTR-CAP@v1 capture-timestamp sidecar."""
        path = episode_dir / RAW_CAPTURE_TS_FILENAME
        if not path.is_file():
            raise CaptureSourceError(f"raw capture_ts sidecar {path} is missing")
        try:
            records = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as bad:
            raise CaptureSourceError(
                f"raw capture_ts sidecar {path} is not valid JSON: {bad}"
            ) from bad
        try:
            return sidecar_from_records(episode_index, records)
        except Exception as bad:  # noqa: BLE001 — any malformed record bars certification
            raise CaptureSourceError(
                f"raw capture_ts sidecar {path} is not a valid CTR-CAP@v1 sidecar: {bad}"
            ) from bad

    def delete(self) -> None:
        """Remove the entire raw capture source tree.

        This is the one irreversible operation in the band. The interlock invokes it
        only behind a `DELETABLE` decision; it performs no checking of its own, so
        every caller must gate it on that decision (`02b` §7.2 WP-3C-06).
        """
        if self.root.is_dir():
            shutil.rmtree(self.root)
