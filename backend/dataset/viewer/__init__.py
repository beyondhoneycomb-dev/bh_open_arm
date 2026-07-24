"""WP-3D-01 episode viewer — direct parquet/mp4 read, no Rerun/dora.

Public surface for the direct-read episode viewer: open a LeRobot v3.0 dataset by
path, and for any cursor time get every configured camera stream (RGB and depth),
the `observation.state` and `action` cursor rows, and the per-joint following
error, all on the synthetic grid axis `timestamp = frame_index / fps`. Stream
count and type come from `meta/info.json`; channel units come from the name
suffix; following error is position-only; limit/`tmax` overlays highlight near and
saturated regions.
"""

from __future__ import annotations

from backend.dataset.viewer.channels import (
    CameraStream,
    FollowingErrorPair,
    ViewerChannelError,
    action_channel_names,
    axis_label,
    camera_streams,
    following_error_pairs,
    state_channel_names,
    unit_for_channel,
)
from backend.dataset.viewer.episode_viewer import EpisodeViewer, ViewerFrame
from backend.dataset.viewer.layout import (
    DatasetLayout,
    DatasetLayoutError,
    EpisodeLocation,
    VideoSegment,
)
from backend.dataset.viewer.overlay import (
    DAMIAO_TMAX_NM,
    BandAnnotation,
    ChannelAnnotation,
    LimitBand,
    LimitKind,
    OverlaySpec,
    annotate,
    annotate_channel,
    torque_band,
)
from backend.dataset.viewer.signals import (
    EpisodeSignals,
    FollowingError,
    TimeAxis,
    read_episode_signals,
)
from backend.dataset.viewer.video import (
    VideoFrameReader,
    ViewerVideoError,
    read_image_frame,
)

__all__ = [
    "DAMIAO_TMAX_NM",
    "BandAnnotation",
    "CameraStream",
    "ChannelAnnotation",
    "DatasetLayout",
    "DatasetLayoutError",
    "EpisodeLocation",
    "EpisodeSignals",
    "EpisodeViewer",
    "FollowingError",
    "FollowingErrorPair",
    "LimitBand",
    "LimitKind",
    "OverlaySpec",
    "TimeAxis",
    "VideoFrameReader",
    "VideoSegment",
    "ViewerChannelError",
    "ViewerFrame",
    "ViewerVideoError",
    "action_channel_names",
    "annotate",
    "annotate_channel",
    "axis_label",
    "camera_streams",
    "following_error_pairs",
    "read_episode_signals",
    "read_image_frame",
    "state_channel_names",
    "torque_band",
    "unit_for_channel",
]
