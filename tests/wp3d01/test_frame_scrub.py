"""All-camera + state + action synchronized on one axis, with packed-segment offset.

`FR-DAT-011`: RGB (mp4), depth (per-frame TIFF), `observation.state` and `action`
are read for the same grid frame and returned together. The packed dataset holds
two episodes in one data file and one mp4, so this also proves the reader slices
by `episode_index` and offsets video by `from_timestamp` — episode 1 frame 0 must
decode the eighth global frame, not the first.
"""

from __future__ import annotations

import numpy as np

from backend.dataset.viewer.episode_viewer import EpisodeViewer
from tests.wp3d01.materialize import MaterializedDataset


def _assert_synchronized_frame(
    viewer: EpisodeViewer, dataset: MaterializedDataset, episode: int, frame: int
) -> None:
    view = viewer.frame_by_index(frame)
    assert view.frame_index == frame
    assert view.grid_seconds == frame / dataset.fps

    # Every configured stream is present, decoded to the right kind of array.
    assert set(view.images) == {*dataset.rgb_keys, dataset.depth_key}
    for rgb_key in dataset.rgb_keys:
        image = view.images[rgb_key]
        assert image.shape == (8, 8, 3)
        assert image.dtype == np.uint8
        # The decoded solid luma identifies the *global* frame, proving the segment
        # offset (from_timestamp) was applied for this episode.
        assert abs(float(image.mean()) - dataset.expected_luma(episode, frame)) <= 2.0

    depth = view.images[dataset.depth_key]
    assert depth.shape == (8, 8)
    assert depth.dtype == np.uint16
    base = dataset.expected_depth_value(episode, frame)
    assert depth.min() == base

    # State and action carry every channel on the same frame.
    assert len(view.state) == len(viewer.signals.state_names)
    assert len(view.action) == len(viewer.signals.action_names)


def test_episode0_frames_synchronized(
    episode0: EpisodeViewer, dataset: MaterializedDataset
) -> None:
    for frame in range(dataset.frames):
        _assert_synchronized_frame(episode0, dataset, episode=0, frame=frame)


def test_episode1_segment_offset(episode1: EpisodeViewer, dataset: MaterializedDataset) -> None:
    # Episode 1 frame 0 is global frame 8 in the packed mp4 (luma 120), not frame 0.
    view = episode1.frame_by_index(0)
    assert abs(float(view.images[dataset.rgb_keys[0]].mean()) - dataset.expected_luma(1, 0)) <= 2.0
    assert dataset.expected_luma(1, 0) != dataset.expected_luma(0, 0)
    for frame in range(dataset.frames):
        _assert_synchronized_frame(episode1, dataset, episode=1, frame=frame)


def test_state_action_match_fixture(episode0: EpisodeViewer) -> None:
    # The fixture ramps action position by 1.0 deg per frame from 0; the recorded
    # observation follows it. Assert action is the per-frame ramp on the shared axis.
    for frame in range(episode0.time_axis.frame_count()):
        view = episode0.frame_by_index(frame)
        for name, value in view.action.items():
            assert name.endswith(".pos")
            assert value == float(frame)


def test_step_moves_one_frame(episode0: EpisodeViewer) -> None:
    stepped = episode0.step(2, +1)
    assert stepped.frame_index == 3
    assert episode0.step(0, -1).frame_index == 0  # clamped at the low end
