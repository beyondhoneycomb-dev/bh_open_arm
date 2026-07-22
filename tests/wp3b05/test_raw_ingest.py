"""WP-3B-05 ① — collection records lossless PNG originals (depth 16-bit TIFF).

Stage 1 writes the *original* frame, not a transcode: RGB as lossless PNG and depth
as 16-bit TIFF (`15` NFR-PRF-028, `06` §2.8). These prove it on the synthetic camera
fixture — the files land under the contract-named pattern, and a decode round-trips
the pixels exactly, which is what "lossless" has to mean for the later transcode to
be checkable against them.
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.sensing.encoding import RawEpisodeStore, RawIngestError, decode_frame, encode_frame
from contracts.prim import FrameType
from tests.wp3b05.support import depth_camera, frame_array, ingest_episode, rgb_camera, stream_of


def test_rgb_frames_are_ingested_as_png(tmp_path):
    """Each RGB frame lands as a `frame-000000.png` original under its slot key."""
    store = RawEpisodeStore(root=tmp_path, episode_index=0)
    camera = rgb_camera()
    stream = ingest_episode(store, camera, frame_count=4)

    paths = store.frame_paths(stream)
    assert [path.name for path in paths] == [f"frame-{i:06d}.png" for i in range(4)]
    assert store.frame_count(stream) == 4
    assert all(path.suffix == ".png" for path in paths)


def test_depth_frames_are_ingested_as_tiff(tmp_path):
    """Each depth frame lands as a 16-bit `frame-000000.tiff` original."""
    store = RawEpisodeStore(root=tmp_path, episode_index=0)
    camera = depth_camera()
    stream = ingest_episode(store, camera, frame_count=3)

    paths = store.frame_paths(stream)
    assert [path.name for path in paths] == [f"frame-{i:06d}.tiff" for i in range(3)]
    assert store.stream_dir(stream).name.endswith("_depth")


def test_png_ingest_is_lossless(tmp_path):
    """A stored RGB original decodes back to the exact pixels that were ingested."""
    store = RawEpisodeStore(root=tmp_path, episode_index=0)
    camera = rgb_camera()
    stream = stream_of(camera)
    frame = camera.read(0)
    assert frame is not None
    original = frame_array(frame)

    path = store.ingest(stream, 0, original)
    restored = decode_frame(path)
    assert np.array_equal(restored, original)


def test_depth_tiff_ingest_preserves_uint16(tmp_path):
    """A stored depth original round-trips as uint16 with its values intact."""
    store = RawEpisodeStore(root=tmp_path, episode_index=0)
    camera = depth_camera()
    stream = stream_of(camera)
    frame = camera.read(0)
    assert frame is not None
    original = frame_array(frame)
    assert original.dtype == np.uint16

    path = store.ingest(stream, 0, original)
    restored = decode_frame(path)
    assert restored.dtype == np.uint16
    assert np.array_equal(restored, original)


def test_wrong_dtype_is_refused():
    """A uint8 array offered as a depth frame is a contract violation, not upcast."""
    not_depth = np.zeros((16, 16), dtype=np.uint8)
    with pytest.raises(RawIngestError):
        encode_frame(FrameType.DEPTH, not_depth)


def test_wrong_channel_count_is_refused():
    """An RGB frame must be three-channel; a single plane is refused."""
    single_plane = np.zeros((16, 16), dtype=np.uint8)
    with pytest.raises(RawIngestError):
        encode_frame(FrameType.RGB, single_plane)
