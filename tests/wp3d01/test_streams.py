"""Acceptance ①: stream count and type come from info.json, no fixed slots.

`FR-DAT-011`: the viewer derives which camera streams exist, and whether each is
RGB or depth, from the dataset's `meta/info.json` feature set — never a hardcoded
slot list. These tests prove enumeration over the materialized dataset and over a
hand-built info.json with unrelated slot names, plus depth classification by the
`is_depth_map` flag.
"""

from __future__ import annotations

from backend.dataset.viewer import DatasetLayout, camera_streams
from backend.dataset.viewer.channels import FrameType
from tests.wp3d01.materialize import MaterializedDataset


def test_streams_enumerated_from_info_json(dataset: MaterializedDataset) -> None:
    layout = DatasetLayout(dataset.root)
    streams = {stream.image_key: stream for stream in layout.camera_streams()}

    # Exactly the configured streams: two RGB cameras plus one depth camera.
    assert set(streams) == {*dataset.rgb_keys, dataset.depth_key}
    for rgb_key in dataset.rgb_keys:
        assert streams[rgb_key].frame_type == FrameType.RGB
        assert not streams[rgb_key].is_depth
    assert streams[dataset.depth_key].frame_type == FrameType.DEPTH
    assert streams[dataset.depth_key].is_depth


def test_depth_and_rgb_share_a_slot(dataset: MaterializedDataset) -> None:
    layout = DatasetLayout(dataset.root)
    streams = {stream.image_key: stream for stream in layout.camera_streams()}
    # The depth stream's base slot is the RGB camera it belongs to, not "<slot>_depth".
    depth_slot = streams[dataset.depth_key].slot.value
    assert any(streams[rgb].slot.value == depth_slot for rgb in dataset.rgb_keys)


def test_no_fixed_slot_assumption() -> None:
    # A dataset whose cameras are named nothing like the fixture's must still be
    # enumerated correctly — the count and type are read, not assumed.
    features = {
        "observation.state": {"names": ["joint_1.pos"]},
        "action": {"names": ["joint_1.pos"]},
        "observation.images.overhead": {"dtype": "video", "shape": ["height", "width", 3]},
        "observation.images.overhead_depth": {
            "dtype": "uint16",
            "shape": [4, 4, 1],
            "is_depth_map": True,
        },
        "observation.images.gripper_cam": {"dtype": "video", "shape": ["height", "width", 3]},
    }
    streams = camera_streams(features)
    keys = {stream.image_key: stream for stream in streams}
    assert set(keys) == {
        "observation.images.overhead",
        "observation.images.overhead_depth",
        "observation.images.gripper_cam",
    }
    assert keys["observation.images.overhead"].frame_type == FrameType.RGB
    assert keys["observation.images.overhead_depth"].frame_type == FrameType.DEPTH
    assert keys["observation.images.gripper_cam"].frame_type == FrameType.RGB


def test_depth_classified_by_flag_even_without_suffix() -> None:
    # A depth stream flagged is_depth_map but not carrying the _depth suffix is
    # still classified as depth: the flag is authoritative.
    features = {
        "observation.state": {"names": ["joint_1.pos"]},
        "action": {"names": ["joint_1.pos"]},
        "observation.images.front": {"dtype": "uint16", "shape": [4, 4, 1], "is_depth_map": True},
    }
    (stream,) = camera_streams(features)
    assert stream.frame_type == FrameType.DEPTH
