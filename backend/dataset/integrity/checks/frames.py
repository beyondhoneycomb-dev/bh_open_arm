"""Check 4 — encoded frame count matches declared length (`02b` §8.2 WP-3D-05).

Each RGB camera's frames are packed into one mp4 across every episode, so the mp4
must hold exactly the sum of the lengths of the episodes that reference it; each
depth camera stores one TIFF per frame, so its per-episode directory must hold
exactly `length` files. A mismatch means a frame was dropped or duplicated during
encoding — the video and the state/action rows would then desynchronise, and the
following-error a viewer computes would line a command up against the wrong image.

The mp4 count is taken by demuxing packets, not decoding pixels: one coded frame
is one packet, so the count is exact while the cost stays proportional to reading
the file once, which the regression bound (`WP-3D-05 ③`) requires.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import av

from backend.dataset.integrity.constants import CHECK_VIDEO_FRAME_COUNT
from backend.dataset.integrity.dataset import DatasetInventory, InventoryError
from backend.dataset.integrity.report import CheckResult, failed, passed
from backend.dataset.viewer.constants import DEPTH_IMAGE_PATH_TEMPLATE


def _demux_frame_count(path: Path) -> int:
    """Count coded frames in an mp4 by demuxing packets, without decoding pixels.

    Raises:
        ValueError: When the container has no video stream.
        Exception: Any PyAV failure opening or demuxing a corrupt container.
    """
    with av.open(str(path)) as container:
        if not container.streams.video:
            raise ValueError(f"{path} carries no video stream")
        stream = container.streams.video[0]
        return sum(1 for packet in container.demux(stream) if packet.size > 0)


def _depth_frame_count(root: Path, image_key: str, episode_index: int) -> int:
    """Count the per-frame depth TIFFs written for one episode of a depth stream."""
    sample = DEPTH_IMAGE_PATH_TEMPLATE.format(
        image_key=image_key, episode_index=episode_index, frame_index=0
    )
    episode_dir = (root / sample).parent
    if not episode_dir.is_dir():
        return 0
    return sum(1 for _ in episode_dir.glob("frame-*.tiff"))


def check_video_frame_count(inventory: DatasetInventory) -> CheckResult:
    """Verify each mp4's frame count and each depth directory's file count match length.

    Args:
        inventory: The shared dataset read.

    Returns:
        (CheckResult) PASS when every stream's frame count equals the declared
            length(s); FAIL naming the first stream that disagrees.
    """
    try:
        layout = inventory.require_layout()
    except InventoryError as bad:
        return failed(CHECK_VIDEO_FRAME_COUNT, f"layout unreadable: {bad}")

    expected_per_video: dict[Path, int] = defaultdict(int)
    checked = 0

    for episode_index in layout.episode_indices() or (0,):
        location = layout.locate(episode_index)
        length = location.length
        for segment in location.video_segments.values():
            expected_per_video[segment.file] += length
        for stream in layout.camera_streams():
            if not stream.is_depth:
                continue
            actual = _depth_frame_count(layout.root, stream.image_key, episode_index)
            if actual != length:
                return failed(
                    CHECK_VIDEO_FRAME_COUNT,
                    f"depth {stream.image_key} episode {episode_index} has {actual} TIFF(s), "
                    f"expected length {length}",
                )
            checked += 1

    for video_path, expected in sorted(expected_per_video.items()):
        try:
            actual = _demux_frame_count(video_path)
        except Exception as bad:  # noqa: BLE001 — an undecodable video is a frame-count failure
            return failed(CHECK_VIDEO_FRAME_COUNT, f"{video_path}: cannot count frames ({bad})")
        if actual != expected:
            return failed(
                CHECK_VIDEO_FRAME_COUNT,
                f"{video_path} holds {actual} frame(s), episodes declare {expected}",
            )
        checked += 1

    if checked == 0:
        return failed(
            CHECK_VIDEO_FRAME_COUNT, "dataset declares no video or depth streams to count"
        )

    return passed(
        CHECK_VIDEO_FRAME_COUNT, f"{checked} stream segment(s) match their declared length"
    )
