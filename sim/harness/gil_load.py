"""The synthetic GIL-load generator — five-stream grab, PNG write, dataset write, WS serialize.

This reproduces the *shape* of `15` §2.10 condition 4 (camera 5-stream + lossless-PNG
frame write + dataset write + GUI/WS serialization in one process) as a synthetic
workload, with no real cameras (`02a` WP-0C-06 deliverable). It is an approximation,
not an upper bound (03 §5.1a).

Why a Python-bytecode spin sits at the centre of each load tick. The phenomenon
`PG-RT-001` measures is GIL *contention*, not CPU load in general: a control loop is
delayed only while another thread in the same interpreter holds the GIL when the
loop wakes. zlib compression and file writes release the GIL, so on their own they
would not model contention at all — they would run happily beside the victim loop
and prove nothing. The honest model therefore concentrates the *Python-held* portion
of a real grab/encode/serialize pipeline (the per-frame orchestration that never
leaves the interpreter) into an explicit bytecode spin whose size scales with the
four load parameters. When the parameters are zero the spin is zero, which is what
lets acceptance ③ distinguish a biting load from a no-load harness.

The generator runs identically as a same-process thread (condition 4) or a
separate-process worker (condition 5); the only difference is which interpreter's
GIL it contends for, and that difference is exactly the GIL contribution
(acceptance ④).
"""

from __future__ import annotations

import multiprocessing as mp
import threading
import time
import zlib
from enum import Enum
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Protocol

import numpy as np

from sim.harness.load_profile import LoadProfile

if TYPE_CHECKING:
    from multiprocessing.process import BaseProcess
    from multiprocessing.synchronize import Event as MpEvent

# One synthetic frame is 3 bytes/pixel (RGB), the shape a real grab hands to the
# encoder. Only used to size the buffer; depth/other streams share the same model.
_BYTES_PER_PIXEL = 3

# The bytecode spin runs `stream_count * (png_bytes + serialize_bytes) // _SPIN_DIVISOR`
# integer iterations per load tick. The divisor is tuned so a realistic load profile
# (5 streams, tens of KB/frame) produces a spin long enough to hold the GIL across a
# meaningful fraction of a control period — i.e. long enough to actually delay a victim
# loop — while a zero-byte or zero-stream profile spins zero times. It carries no
# physical meaning; it is the one free knob that sets how hard the synthetic load
# leans on the interpreter, and it is recorded nowhere as a result because it is not
# a measurement, only the load's intensity.
_SPIN_DIVISOR = 8

# The compression stage models the CPU of lossless encoding, which releases the GIL.
# Level 1 (Z_BEST_SPEED) keeps it lossless but fast, and the input is capped so a
# large frame's compression cannot dominate the tick and starve the GIL-holding spin
# of its share of the interval — the spin is what models contention, not the encoder.
_COMPRESSION_LEVEL = 1
_MAX_COMPRESS_BYTES = 128 * 1024

# The rolling dataset file is reset to its start once it passes this size, so a long
# run writes real bytes to disk continuously without growing without bound.
_DATASET_ROLL_BYTES = 8 * 1024 * 1024

# A worker must drain within this many seconds of being asked to stop; past it the
# separate-process worker is terminated so a wedged load can never hang the harness.
_JOIN_TIMEOUT_SEC = 5.0

# A no-load profile's worker yields the GIL this often instead of tight-looping on the
# stop flag. Without it, an empty load loop would busy-hold the GIL and inflate the
# victim even with zero declared load, breaking the acceptance ③ anti-rig property
# (a no-load harness must not be distinguishable from idle).
_IDLE_YIELD_SEC = 1e-3


class StopFlag(Protocol):
    """The minimal stop signal both `threading.Event` and `mp.Event` satisfy."""

    def is_set(self) -> bool:
        """Whether the load has been asked to stop."""
        ...


class LoadLocation(Enum):
    """Where the synthetic load runs relative to the victim control loop.

    NONE is the idle baseline (condition 1). SAME_PROCESS is the canonical
    contention case (condition 4). SEPARATE_PROCESS is the process-separation
    experiment (condition 5); its whole point is that the load cannot touch the
    victim's GIL, so `SAME_PROCESS - SEPARATE_PROCESS` is the GIL contribution.
    """

    NONE = "none"
    SAME_PROCESS = "same_process"
    SEPARATE_PROCESS = "separate_process"


def _gil_spin_iterations(profile: LoadProfile) -> int:
    """Return how many bytecode iterations one load tick holds the GIL for.

    Args:
        profile: The four-parameter load profile.

    Returns:
        (int) Iteration count, zero exactly when the profile exerts no load.
    """
    per_stream_bytes = profile.png_write_bytes_per_frame + profile.serialize_bytes_per_tick
    return profile.stream_count * per_stream_bytes // _SPIN_DIVISOR


def _spin_python(iterations: int) -> int:
    """Hold the GIL for `iterations` pure-Python integer steps.

    This is deliberately un-vectorised: a numpy loop would release the GIL and defeat
    the purpose. The returned accumulator keeps the optimiser from eliding the loop.

    Args:
        iterations: How many integer steps to run.

    Returns:
        (int) An accumulator derived from the loop, used only to keep it live.
    """
    accumulator = 0
    for step in range(iterations):
        accumulator = (accumulator + step) & 0xFFFFFFFF
    return accumulator


def simulate_grab(profile: LoadProfile) -> list[np.ndarray]:
    """Allocate and fill `stream_count` synthetic frames — the camera-grab stage.

    Args:
        profile: The load profile giving stream count and resolution.

    Returns:
        (list[np.ndarray]) One `uint8` HxWx3 buffer per stream. Allocation and the
        fill run per stream in a Python loop; the fill itself releases the GIL, as a
        real driver's C grab does.
    """
    width, height = profile.resolution
    frames: list[np.ndarray] = []
    for stream in range(profile.stream_count):
        frame = np.empty((height, width, _BYTES_PER_PIXEL), dtype=np.uint8)
        frame.fill(stream & 0xFF)
        frames.append(frame)
    return frames


def encode_lossless_png(frame: np.ndarray, target_bytes: int) -> bytes:
    """Losslessly compress a frame and size the result to the PNG write budget.

    zlib at maximum level models the CPU of lossless PNG encoding (a real encoder
    also runs DEFLATE). The output is padded or truncated to `target_bytes` so the
    downstream write moves exactly the profile's declared bytes-per-frame.

    Args:
        frame: The HxWx3 frame buffer.
        target_bytes: The PNG-write budget in bytes per frame.

    Returns:
        (bytes) Exactly `target_bytes` bytes to write for this frame.
    """
    raw = frame.tobytes()[:_MAX_COMPRESS_BYTES]
    compressed = zlib.compress(raw, level=_COMPRESSION_LEVEL)
    if len(compressed) >= target_bytes:
        return compressed[:target_bytes]
    return compressed + bytes(target_bytes - len(compressed))


def serialize_ws(profile: LoadProfile, tick: int) -> bytes:
    """Serialize one WS/GUI tick to its declared byte budget — the transmit stage.

    Args:
        profile: The load profile giving the per-tick serialization budget.
        tick: The current load-tick index, folded in so the payload varies.

    Returns:
        (bytes) A `serialize_bytes_per_tick`-byte payload. `tobytes` on a numpy
        buffer models the copy a real serializer makes into the send buffer.
    """
    size = profile.serialize_bytes_per_tick
    if size == 0:
        return b""
    payload = np.full(size, tick & 0xFF, dtype=np.uint8)
    return payload.tobytes()


def run_load(
    profile: LoadProfile,
    stop_flag: StopFlag,
    dataset_dir: str,
    active_flag: StopFlag | None = None,
) -> None:
    """Run the four-stage synthetic load until `stop_flag` is set.

    Each tick grabs every stream, encodes and writes a PNG per stream, appends to a
    rolling dataset file, serializes the WS payload, and spins the GIL for the
    param-scaled interval. The dataset file rolls back to its start past a cap so
    disk stays bounded across a long run.

    When an `active_flag` is given, the load only does work while the flag is set and
    yields the GIL otherwise. This lets the interleaved measurement gate contention on
    and off inside one continuous run, so machine drift is shared between the loaded
    and unloaded cycles it is compared across.

    Args:
        profile: The four-parameter load profile.
        stop_flag: The stop signal; either a `threading.Event` or an `mp.Event`.
        dataset_dir: Directory the PNG and dataset bytes are written under.
        active_flag: Optional gate; when present, work runs only while it is set.
    """
    if profile.is_no_load:
        while not stop_flag.is_set():
            time.sleep(_IDLE_YIELD_SEC)
        return

    directory = Path(dataset_dir)
    directory.mkdir(parents=True, exist_ok=True)
    dataset_path = directory / "dataset.bin"
    frame_path = directory / "frames.png"
    spin_iterations = _gil_spin_iterations(profile)

    tick = 0
    written = 0
    with dataset_path.open("wb") as dataset_file, frame_path.open("wb") as frame_file:
        while not stop_flag.is_set():
            if active_flag is not None and not active_flag.is_set():
                time.sleep(_IDLE_YIELD_SEC)
                continue
            frames = simulate_grab(profile)
            for frame in frames:
                png = encode_lossless_png(frame, profile.png_write_bytes_per_frame)
                frame_file.seek(0)
                frame_file.write(png)
            payload = serialize_ws(profile, tick)
            if written + len(payload) > _DATASET_ROLL_BYTES:
                dataset_file.seek(0)
                written = 0
            dataset_file.write(payload)
            written += len(payload)
            _spin_python(spin_iterations)
            tick += 1


class LoadRunner:
    """A context manager that starts the synthetic load and guarantees it stops.

    Ownership: owns the worker (a thread for SAME_PROCESS, a process for
    SEPARATE_PROCESS) and its stop signal for the lifetime of the `with` block, and
    joins it on exit so no load outlives the measurement it was created for. NONE
    owns nothing and does nothing — it is the idle baseline.
    """

    def __init__(self, profile: LoadProfile, location: LoadLocation, dataset_dir: str) -> None:
        """Prepare a load runner; no worker starts until the block is entered.

        Args:
            profile: The load profile to run.
            location: Where the load runs relative to the victim loop.
            dataset_dir: Directory the load writes its PNG and dataset bytes under.
        """
        self.profile = profile
        self.location = location
        self.dataset_dir = dataset_dir
        self._thread: threading.Thread | None = None
        self._process: BaseProcess | None = None
        self._thread_stop: threading.Event | None = None
        self._process_stop: MpEvent | None = None

    def __enter__(self) -> LoadRunner:
        """Start the worker for a non-NONE location and let it spin up."""
        if self.location is LoadLocation.SAME_PROCESS:
            self._thread_stop = threading.Event()
            self._thread = threading.Thread(
                target=run_load,
                args=(self.profile, self._thread_stop, self.dataset_dir),
                name="gil-load-thread",
                daemon=True,
            )
            self._thread.start()
        elif self.location is LoadLocation.SEPARATE_PROCESS:
            context = mp.get_context("fork")
            self._process_stop = context.Event()
            self._process = context.Process(
                target=run_load,
                args=(self.profile, self._process_stop, self.dataset_dir),
                name="gil-load-process",
                daemon=True,
            )
            self._process.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Signal the worker to stop and join it, so nothing outlives the block."""
        if self._thread is not None and self._thread_stop is not None:
            self._thread_stop.set()
            self._thread.join(timeout=_JOIN_TIMEOUT_SEC)
        if self._process is not None and self._process_stop is not None:
            self._process_stop.set()
            self._process.join(timeout=_JOIN_TIMEOUT_SEC)
            if self._process.is_alive():
                self._process.terminate()
                self._process.join(timeout=_JOIN_TIMEOUT_SEC)
