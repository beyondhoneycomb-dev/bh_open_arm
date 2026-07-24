"""Read the converted LeRobot v3.0 dataset's capture-relevant facets.

The converted dataset is read through the committed WP-3D-01 viewer `DatasetLayout`
— the same v3.0 storage convention consumed as data (`06` §5.6), never a second
parser. This module adds only the projections the four capture-preservation checks
need beyond a viewer: the encoded frame count of each stream, the declared temporal
extent of each video, the actual data-parquet row count of an episode, and the
converted copy of the CTR-CAP@v1 capture-timestamp sidecar.

Frame counting demuxes packets rather than decoding pixels — one coded frame is one
packet — so the cost stays proportional to reading the file once. The row count is
the *actual* number of parquet rows carrying the episode's index, not the declared
`dataset_from/to_index` range, so a dropped or duplicated row is caught rather than
trusted from the metadata that a faithful conversion would also have had to update.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import av
import pyarrow.parquet as pq

from backend.capture_interlock.constants import CONVERTED_CAPTURE_SIDECAR_TEMPLATE
from backend.dataset.viewer.constants import (
    DEPTH_IMAGE_PATH_TEMPLATE,
    EPISODE_INDEX_COLUMN,
)
from backend.dataset.viewer.layout import DatasetLayout
from contracts.capture.schema import CaptureSidecar, sidecar_from_records


class ConvertedReadError(ValueError):
    """Raised when a converted-dataset facet the interlock needs cannot be read.

    A missing capture_ts sidecar, an undecodable video, or an unreadable data
    parquet each raise; the check that needs the facet turns the error into a FAIL,
    so a facet that cannot be established never silently passes a preservation check.
    """


@dataclass(frozen=True)
class StreamFrameCount:
    """The encoded frame count of one converted stream for one episode.

    Attributes:
        image_key: The stream's `observation.images.*` feature key.
        is_depth: Whether the stream is depth (per-frame TIFF) rather than RGB (mp4).
        frame_count: The encoded frames found — demuxed packets for mp4, TIFF files
            for depth.
    """

    image_key: str
    is_depth: bool
    frame_count: int


@dataclass(frozen=True)
class VideoDeclaredSpan:
    """One converted video's declared temporal extent, in frames, for one episode.

    Derived from the episode metadata's `[from_timestamp, to_timestamp]` segment:
    the inclusive frame span is `round((to - from) * fps) + 1`. This is what the
    episode metadata *claims* the video covers, independent of the bytes on disk, so
    check ② can catch a claim that no longer matches the original episode length.

    Attributes:
        image_key: The video stream's feature key.
        declared_frames: The frame count the declared segment spans.
    """

    image_key: str
    declared_frames: int


class ConvertedDataset:
    """A converted v3.0 dataset, read for the capture-preservation checks.

    Ownership: holds no file handles; builds the viewer layout once at construction
    and resolves per-episode facets on demand. Read-only — nothing here mutates the
    converted dataset (the interlock's flag write lives in `interlock`).
    """

    def __init__(self, root: Path) -> None:
        """Build the viewer layout for a converted dataset root.

        Args:
            root: The converted dataset root (the directory holding `meta/`,
                `data/`, `videos/`).

        Raises:
            DatasetLayoutError: If the dataset cannot be read as a v3.0 dataset.
        """
        self.root = Path(root)
        self.layout = DatasetLayout(self.root)

    @property
    def fps(self) -> int:
        """The dataset frame rate from `info.json`."""
        return self.layout.fps

    def episode_indices(self) -> tuple[int, ...]:
        """The episode indices the converted dataset declares, ascending."""
        return self.layout.episode_indices()

    def declared_length(self, episode_index: int) -> int:
        """The frame count the episode metadata declares for an episode."""
        return self.layout.locate(episode_index).length

    def stream_frame_counts(self, episode_index: int) -> tuple[StreamFrameCount, ...]:
        """The encoded frame count of every converted stream for an episode.

        RGB streams are counted by demuxing their packed mp4; depth streams are
        counted by the per-frame TIFFs in the episode's depth directory.

        Args:
            episode_index: The episode to measure.

        Returns:
            (tuple[StreamFrameCount, ...]) One entry per configured stream.

        Raises:
            ConvertedReadError: If a video cannot be opened or demuxed.
        """
        location = self.layout.locate(episode_index)
        counts: list[StreamFrameCount] = []
        for stream in self.layout.camera_streams():
            if stream.is_depth:
                counts.append(
                    StreamFrameCount(
                        image_key=stream.image_key,
                        is_depth=True,
                        frame_count=self._depth_frame_count(stream.image_key, episode_index),
                    )
                )
                continue
            segment = location.video_segments.get(stream.image_key)
            if segment is None:
                raise ConvertedReadError(
                    f"episode {episode_index} stream {stream.image_key!r} has no video segment"
                )
            counts.append(
                StreamFrameCount(
                    image_key=stream.image_key,
                    is_depth=False,
                    frame_count=self._demux_frame_count(segment.file),
                )
            )
        return tuple(counts)

    def video_declared_spans(self, episode_index: int) -> tuple[VideoDeclaredSpan, ...]:
        """The declared temporal frame span of every RGB video for an episode.

        Depth streams carry no `[from, to]` segment (they are per-frame TIFFs), so
        they contribute no declared span — check ② is a video-length check, and
        depth has no video length to declare.

        Args:
            episode_index: The episode to measure.

        Returns:
            (tuple[VideoDeclaredSpan, ...]) One entry per RGB video segment.
        """
        location = self.layout.locate(episode_index)
        spans: list[VideoDeclaredSpan] = []
        for image_key, segment in sorted(location.video_segments.items()):
            span_seconds = segment.to_timestamp - segment.from_timestamp
            declared_frames = round(span_seconds * self.fps) + 1
            spans.append(VideoDeclaredSpan(image_key=image_key, declared_frames=declared_frames))
        return tuple(spans)

    def parquet_row_count(self, episode_index: int) -> int:
        """The actual number of data-parquet rows carrying an episode's index.

        Args:
            episode_index: The episode to count rows for.

        Returns:
            (int) The number of rows whose `episode_index` column equals the episode.

        Raises:
            ConvertedReadError: If the data parquet cannot be read.
        """
        data_file = self.layout.locate(episode_index).data_file
        if not data_file.is_file():
            raise ConvertedReadError(f"data parquet {data_file} is missing")
        try:
            column = pq.read_table(data_file, columns=[EPISODE_INDEX_COLUMN]).column(
                EPISODE_INDEX_COLUMN
            )
        except Exception as bad:  # noqa: BLE001 — an unreadable parquet is a row-count failure
            raise ConvertedReadError(f"data parquet {data_file} is unreadable: {bad}") from bad
        return sum(1 for value in column.to_pylist() if int(value) == episode_index)

    def capture_sidecar(self, episode_index: int) -> CaptureSidecar:
        """The converted copy of an episode's CTR-CAP@v1 capture-timestamp sidecar.

        Args:
            episode_index: The episode to read.

        Returns:
            (CaptureSidecar) The preserved capture-timestamp sidecar.

        Raises:
            ConvertedReadError: If the sidecar is missing or is not a valid sidecar.
        """
        path = self.root / CONVERTED_CAPTURE_SIDECAR_TEMPLATE.format(episode_index=episode_index)
        if not path.is_file():
            raise ConvertedReadError(f"converted capture_ts sidecar {path} is missing")
        try:
            records = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as bad:
            raise ConvertedReadError(
                f"converted capture_ts sidecar {path} is not valid JSON: {bad}"
            ) from bad
        try:
            return sidecar_from_records(episode_index, records)
        except Exception as bad:  # noqa: BLE001 — a malformed sidecar is a preservation failure
            raise ConvertedReadError(
                f"converted capture_ts sidecar {path} is not a valid CTR-CAP@v1 sidecar: {bad}"
            ) from bad

    def _depth_frame_count(self, image_key: str, episode_index: int) -> int:
        """Count the per-frame depth TIFFs written for one episode of a depth stream."""
        sample = DEPTH_IMAGE_PATH_TEMPLATE.format(
            image_key=image_key, episode_index=episode_index, frame_index=0
        )
        episode_dir = (self.root / sample).parent
        if not episode_dir.is_dir():
            return 0
        return sum(1 for _ in episode_dir.glob("frame-*.tiff"))

    def _demux_frame_count(self, path: Path) -> int:
        """Count coded frames in an mp4 by demuxing packets, without decoding pixels."""
        try:
            with av.open(str(path)) as container:
                if not container.streams.video:
                    raise ConvertedReadError(f"{path} carries no video stream")
                stream = container.streams.video[0]
                return sum(1 for packet in container.demux(stream) if packet.size > 0)
        except ConvertedReadError:
            raise
        except Exception as bad:  # noqa: BLE001 — an undecodable video is a frame-count failure
            raise ConvertedReadError(f"{path} cannot be demuxed: {bad}") from bad
