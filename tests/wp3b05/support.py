"""Shared helpers for the WP-3B-05 encoding-worker tests.

The tests run against the `02b` §5.2 WP-3A-06 synthetic camera fixture — the
mandated 3B test target, with no real camera touched. These helpers turn a
`SyntheticFrame` into the pixel array stage-1 ingest expects, build configured
synthetic cameras, and provide a controllable transcoder the orchestration tests
drive to prove the worker is off the recording path.
"""

from __future__ import annotations

import threading
from pathlib import Path

import numpy as np

from backend.sensing.encoding import (
    RawEpisodeStore,
    RawStreamRef,
    StreamTranscode,
    TranscodeJob,
    TranscodeResult,
)
from contracts.camera_registry import CameraSpec, make_top_level_camera
from contracts.fixtures.synthetic_camera import SyntheticCamera, SyntheticFrame
from contracts.prim import (
    FRAME_TYPE_CHANNELS,
    FRAME_TYPE_DTYPE,
    CameraSlotKey,
    FrameType,
)

# Even dimensions so the verification codec's yuv420p sampling accepts the frame.
FIXTURE_WIDTH = 16
FIXTURE_HEIGHT = 16
FIXTURE_FPS = 30


def frame_array(frame: SyntheticFrame) -> np.ndarray:
    """Reshape a synthetic frame's bytes into its `CTR-PRIM@v1` frame-type array.

    The dtype and channel count come from the frozen frame-type facts, not from a
    number invented here, so a depth frame is uint16 single-channel and RGB is
    uint8 three-channel exactly as the contract fixes.

    Args:
        frame: The synthetic frame whose bytes are reshaped.

    Returns:
        (np.ndarray) A writable pixel array in the frame's contract shape.
    """
    dtype = np.dtype(FRAME_TYPE_DTYPE[frame.frame_type])
    channels = FRAME_TYPE_CHANNELS[frame.frame_type]
    flat = np.frombuffer(frame.data, dtype=dtype)
    if channels == 1:
        return flat.reshape(frame.height, frame.width).copy()
    return flat.reshape(frame.height, frame.width, channels).copy()


def rgb_camera(
    name: str = "front", width: int = FIXTURE_WIDTH, height: int = FIXTURE_HEIGHT
) -> SyntheticCamera:
    """Build a configured RGB synthetic camera at the given geometry."""
    spec: CameraSpec = make_top_level_camera(name, frozenset({FrameType.RGB})).configured(
        width, height, FIXTURE_FPS
    )
    return SyntheticCamera(spec=spec, frame_type=FrameType.RGB)


def depth_camera(name: str = "wrist") -> SyntheticCamera:
    """Build a configured depth synthetic camera at the fixture geometry."""
    spec: CameraSpec = make_top_level_camera(
        name, frozenset({FrameType.RGB, FrameType.DEPTH})
    ).configured(FIXTURE_WIDTH, FIXTURE_HEIGHT, FIXTURE_FPS)
    return SyntheticCamera(spec=spec, frame_type=FrameType.DEPTH)


def stream_of(camera: SyntheticCamera) -> RawStreamRef:
    """The `RawStreamRef` for a synthetic camera's slot and frame kind."""
    return RawStreamRef(slot=camera.slot, frame_type=camera.frame_type)


def ingest_episode(
    store: RawEpisodeStore, camera: SyntheticCamera, frame_count: int
) -> RawStreamRef:
    """Ingest a synthetic camera's live frames into a stage-1 store.

    Args:
        store: The episode store to write originals into.
        camera: The synthetic camera to grab from.
        frame_count: The number of frame indices to walk (0..frame_count-1).

    Returns:
        (RawStreamRef) The stream the frames were written under.
    """
    stream = stream_of(camera)
    for frame in camera.frames(frame_count):
        store.ingest(stream, frame.frame_index, frame_array(frame))
    return stream


def empty_job(root: Path, episode_index: int, slot_name: str = "front") -> TranscodeJob:
    """Build a transcode job over an empty store (for orchestration-only tests)."""
    store = RawEpisodeStore(root=root, episode_index=episode_index)
    stream = RawStreamRef(slot=CameraSlotKey(slot_name), frame_type=FrameType.RGB)
    return TranscodeJob(
        store=store, streams=(stream,), output_dir=root / f"out_{episode_index:06d}"
    )


class ControllableTranscoder:
    """A `transcode_fn` a test can pause, to prove the worker runs off-path.

    It records the thread each transcode ran on and, when given a gate event, blocks
    inside the transcode until the test releases it — so the test can observe that a
    `save_episode()` returned while the previous episode's transcode was still
    running. The result it returns is real: it counts the stored originals.
    """

    def __init__(self, gate: threading.Event | None = None) -> None:
        """Create the transcoder, optionally gated by an event.

        Args:
            gate: When set, the transcode blocks until the event is set.
        """
        self.gate = gate
        self.thread_idents: list[int] = []
        self.episodes: list[int] = []
        self._lock = threading.Lock()

    def __call__(self, job: TranscodeJob) -> TranscodeResult:
        """Record the running thread, optionally block, then count the originals."""
        with self._lock:
            self.thread_idents.append(threading.get_ident())
            self.episodes.append(job.episode_index)
        if self.gate is not None:
            self.gate.wait(timeout=5.0)
        streams = tuple(
            StreamTranscode(
                stream=stream,
                raw_frame_count=job.store.frame_count(stream),
                encoded_frame_count=job.store.frame_count(stream),
                output_path=job.output_dir,
            )
            for stream in job.streams
        )
        return TranscodeResult(episode_index=job.episode_index, streams=streams)
