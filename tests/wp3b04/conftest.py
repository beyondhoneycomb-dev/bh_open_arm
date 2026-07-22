"""Shared helpers for the WP-3B-04 time-sync tests.

The tests run against the `02b` §5.2 WP-3A-06 synthetic camera fixture with injected
jitter — the mandated 3B test target — so a helper turns a `SyntheticCamera` run into
the `TimedFrame` list the synchroniser consumes. No real camera is touched.
"""

from __future__ import annotations

from backend.sensing.timesync.frame import TimedFrame
from contracts.camera_registry import CameraSpec
from contracts.fixtures.synthetic_camera import SyntheticCamera
from contracts.fixtures.synthetic_dataset import default_camera_specs


def configured_spec(index: int) -> CameraSpec:
    """Return one configured default fixture camera spec (width/height/fps all set).

    Args:
        index: The 0-based position in the default fixture camera set.

    Returns:
        (CameraSpec) The configured spec at that position.
    """
    spec = default_camera_specs()[index]
    assert spec.is_configured
    return spec


def spec_fps(spec: CameraSpec) -> int:
    """Return a configured spec's fps as a plain int, narrowing away the None.

    Args:
        spec: A configured camera spec.

    Returns:
        (int) The frames-per-second.
    """
    fps = spec.fps
    assert fps is not None
    return fps


def reconfigured_fps(spec: CameraSpec, fps: int) -> CameraSpec:
    """Return a copy of a configured spec at a different fps, same geometry.

    Args:
        spec: A configured camera spec.
        fps: The frames-per-second to set.

    Returns:
        (CameraSpec) The reconfigured spec.
    """
    assert spec.width is not None and spec.height is not None
    return spec.configured(spec.width, spec.height, fps)


def timed_frames(camera: SyntheticCamera, count: int) -> list[TimedFrame]:
    """Grab a synthetic camera's live frames as `TimedFrame`s in capture order.

    A synthetic frame exposes no sensor clock, so its match timestamp is its
    grab-time capture_ts — the basis `match_timestamp` selects when no sensor is
    present. Dropped indices contribute nothing, exactly as a real grab would.

    Args:
        camera: The synthetic camera to read.
        count: The number of frame indices to walk (0..count-1).

    Returns:
        (list[TimedFrame]) The live frames as timed units.
    """
    frames: list[TimedFrame] = []
    for frame in camera.frames(count):
        frames.append(
            TimedFrame(
                slot=frame.slot,
                frame_index=frame.frame_index,
                match_ts_ns=frame.capture_ts.mono_ns,
                capture_ts_ns=frame.capture_ts.mono_ns,
            )
        )
    return frames
