"""EpisodeViewer — all camera streams, state and action on one grid time axis.

This is the WP-3D-01 surface. Given a dataset root and an episode index it reads
`info.json`, the episode's state/action series and its video segments directly,
then serves any cursor time as a synchronised frame: every configured camera
stream (RGB and depth), the `observation.state` row, the `action` row and the
per-joint following error, all indexed by `round(t * fps)` on the synthetic grid.

The frame lookup opens each stream's container once and reuses it, so a frame
step is a seek and a short decode — the `NFR-DAT-001` path the acceptance bench
times. The viewer holds those open containers; use it as a context manager or
call `close()` so they are released.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from backend.dataset.viewer.channels import CameraStream, axis_label
from backend.dataset.viewer.layout import DatasetLayout, EpisodeLocation
from backend.dataset.viewer.overlay import ChannelAnnotation, OverlaySpec, annotate
from backend.dataset.viewer.signals import (
    EpisodeSignals,
    FollowingError,
    TimeAxis,
    read_episode_signals,
)
from backend.dataset.viewer.video import VideoFrameReader, read_image_frame


class ViewerFrame:
    """One synchronised frame: images plus the state/action/error cursor rows.

    Attributes:
        frame_index: The grid index the cursor resolved to (`round(t * fps)`).
        grid_seconds: `frame_index / fps` — the grid coordinate, not capture time.
        images: Per-stream decoded frame, keyed by `observation.images.*`; RGB is
            `(h, w, 3)` uint8, depth is `(h, w)` uint16.
        state: `observation.state` channel name to value at this frame.
        action: `action` channel name to value at this frame.
        following_error: Motor key to position following error (deg) at this frame.
    """

    def __init__(
        self,
        frame_index: int,
        grid_seconds: float,
        images: dict[str, NDArray[np.generic]],
        state: dict[str, float],
        action: dict[str, float],
        following_error: dict[str, float],
    ) -> None:
        self.frame_index = frame_index
        self.grid_seconds = grid_seconds
        self.images = images
        self.state = state
        self.action = action
        self.following_error = following_error


class EpisodeViewer:
    """A direct-read viewer over one episode of a LeRobot v3.0 dataset."""

    def __init__(self, layout: DatasetLayout, episode_index: int) -> None:
        """Load an episode's layout, signals and video readers.

        Prefer `EpisodeViewer.open`, which builds the layout for a root path.

        Args:
            layout: The dataset layout the episode belongs to.
            episode_index: The zero-based episode to view.
        """
        self.layout = layout
        self.episode_index = episode_index
        self.location: EpisodeLocation = layout.locate(episode_index)
        self.streams: tuple[CameraStream, ...] = layout.camera_streams()
        self.signals: EpisodeSignals = read_episode_signals(layout, episode_index)
        self._following: FollowingError = self.signals.following_error()
        self._video_readers: dict[str, VideoFrameReader] = {
            image_key: VideoFrameReader(segment, layout.fps)
            for image_key, segment in self.location.video_segments.items()
        }

    @classmethod
    def open(cls, root: Path, episode_index: int) -> EpisodeViewer:
        """Open a viewer for an episode of the dataset at `root`.

        Args:
            root: The dataset root directory.
            episode_index: The zero-based episode to view.

        Returns:
            (EpisodeViewer) A ready viewer; close it when done.
        """
        return cls(DatasetLayout(root), episode_index)

    def __enter__(self) -> EpisodeViewer:
        """Enter the viewer's context."""
        return self

    def __exit__(self, *exc: object) -> None:
        """Release open video containers on context exit."""
        self.close()

    @property
    def time_axis(self) -> TimeAxis:
        """The synthetic grid axis the episode is plotted against."""
        return self.signals.time_axis

    @property
    def tasks(self) -> tuple[str, ...]:
        """The task strings labelling this episode."""
        return self.location.tasks

    def axis_label(self, channel: str) -> str:
        """Return a channel's unit-annotated axis label (`FR-DAT-016`)."""
        return axis_label(channel)

    def following_error(self) -> FollowingError:
        """The per-motor position following error series (`FR-DAT-012`)."""
        return self._following

    def state_series_by_channel(self) -> dict[str, NDArray[np.float64]]:
        """Return every `observation.state` channel's series, keyed by name.

        Convenient input to `overlay` for the limit/`tmax` highlighting.
        """
        return {
            name: self.signals.state[:, index]
            for index, name in enumerate(self.signals.state_names)
        }

    def overlay(self, spec: OverlaySpec) -> dict[str, ChannelAnnotation]:
        """Annotate near/saturated regions of state channels against `spec`.

        Args:
            spec: Per-channel limit bands (joint limits, torque `tmax`), supplied
                by the caller from the robot description and follower config.

        Returns:
            (dict[str, ChannelAnnotation]) Highlight masks per annotated channel.
        """
        return annotate(self.state_series_by_channel(), spec)

    def _image(self, stream: CameraStream, frame_index: int) -> NDArray[np.generic]:
        """Decode one stream's frame at a grid index, from mp4 or image sequence."""
        reader = self._video_readers.get(stream.image_key)
        if reader is not None:
            return reader.frame(frame_index)
        return read_image_frame(self.layout.root, stream, self.episode_index, frame_index)

    def frame_by_index(self, frame_index: int) -> ViewerFrame:
        """Assemble the synchronised frame at a grid index.

        Args:
            frame_index: The grid index (clamped into the episode range).

        Returns:
            (ViewerFrame) All camera images plus the state/action/error cursor.
        """
        last = self.time_axis.frame_count() - 1
        index = max(0, min(last, frame_index))
        images = {stream.image_key: self._image(stream, index) for stream in self.streams}
        state = {
            name: float(self.signals.state[index, col])
            for col, name in enumerate(self.signals.state_names)
        }
        action = {
            name: float(self.signals.action[index, col])
            for col, name in enumerate(self.signals.action_names)
        }
        error = {
            motor: float(self._following.error[index, col])
            for col, motor in enumerate(self._following.motors)
        }
        return ViewerFrame(
            frame_index=index,
            grid_seconds=index / self.layout.fps,
            images=images,
            state=state,
            action=action,
            following_error=error,
        )

    def frame_at(self, seconds: float) -> ViewerFrame:
        """Assemble the synchronised frame at a cursor time, via `round(t * fps)`."""
        return self.frame_by_index(self.time_axis.index_at(seconds))

    def step(self, frame_index: int, delta: int) -> ViewerFrame:
        """Return the frame `delta` grid steps from `frame_index` (`FR-DAT-014`)."""
        return self.frame_by_index(frame_index + delta)

    def close(self) -> None:
        """Release every open video container."""
        for reader in self._video_readers.values():
            reader.close()
        self._video_readers.clear()
