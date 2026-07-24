"""Acceptance ②/`FR-DAT-014`: the axis is a grid coordinate, scrub is round(t*fps).

`FR-DAT-010`: the time axis is `timestamp = frame_index / fps`, exact for frame
position and explicitly *not* wall-clock capture time — the viewer must present it
as a grid coordinate. `FR-DAT-014`: the frame for a cursor time is `round(t*fps)`.
"""

from __future__ import annotations

from backend.dataset.viewer.episode_viewer import EpisodeViewer
from tests.wp3d01.materialize import MaterializedDataset


def test_axis_is_not_wall_clock(episode0: EpisodeViewer) -> None:
    axis = episode0.time_axis
    assert axis.is_wall_clock is False
    # The UI note states what the axis is and is not.
    assert "not capture time" in axis.domain_note
    assert "frame_index / fps" in axis.domain_note


def test_axis_timestamps_are_grid_coordinates(
    episode0: EpisodeViewer, dataset: MaterializedDataset
) -> None:
    axis = episode0.time_axis
    assert axis.frame_count() == dataset.frames
    for frame in range(dataset.frames):
        assert axis.timestamps[frame] == frame / dataset.fps
        assert axis.frame_indices[frame] == frame


def test_index_at_rounds_to_nearest_frame(
    episode0: EpisodeViewer, dataset: MaterializedDataset
) -> None:
    axis = episode0.time_axis
    fps = dataset.fps
    # Exactly on a grid point.
    assert axis.index_at(3 / fps) == 3
    # Just below the midpoint rounds down, at/above rounds up (round(t*fps)).
    assert axis.index_at(3.4 / fps) == 3
    assert axis.index_at(3.5 / fps) == 4
    # Out of range clamps into the episode.
    assert axis.index_at(-1.0) == 0
    assert axis.index_at(1000.0) == dataset.frames - 1


def test_frame_at_uses_round(episode0: EpisodeViewer, dataset: MaterializedDataset) -> None:
    frame = episode0.frame_at(2.6 / dataset.fps)
    assert frame.frame_index == 3
