"""The real-time factor `PG-STO-001` is a gate on, and the four conditions it is measured over.

RTF is `elapsed / episode_length`. Above 1 the encoder cannot keep up with the camera, so the
lossless originals stage 1 wrote never get cleared and the disk fills — which is why this is a
gate rather than a performance note. `02b` §6 WP-3C-02 asks for it over four conditions, and the
four are a 2x2 rather than a list: **software (`libsvtav1`) or hardware (`h264_nvenc`) encoder,
crossed with depth included or excluded**. They are separate measurements because the two axes
move RTF for unrelated reasons — the encoder axis moves the CPU/GPU cost per frame, the depth
axis moves how many bytes there are to encode, and a rig can pass one axis and fail the other.

What this module does and does not do:

- It **times** a transcode that someone else supplies. The codec belongs to the caller, so the
  same harness measures the real `libsvtav1` path on a rig and a synthetic one in a test without
  either pretending to be the other.
- It **refuses to invent an episode length**. RTF's denominator is the wall-clock duration of the
  episode that was recorded, not the frame count and not the file size. A harness that derived it
  would be reporting a ratio whose bottom half nobody measured.
- It **does not judge**. `PG-STO-001`'s verdict has a mitigation ladder behind it (isolate the
  worker, switch to the hardware encoder honouring NVENC's 8-session limit, change the capture
  profile) and then a `DEGRADED_ACCEPTED` branch that back-computes an episode ceiling from the
  disk-exhaustion time. That is an operator decision over a whole session's numbers, not a
  boolean this function can return.

The per-stream bytes/second coefficient is measured here too, and acceptance ③ is asymmetric
about it on purpose: an **under**-estimate must be raised, an over-estimate is allowed to stand.
The asymmetry is the whole point — a coefficient that is too small makes a disk look like it will
last longer than it will, and the failure lands as an out-of-space mid-session with originals
that cannot be cleared.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

# Where RTF stops being survivable. At exactly 1 the encoder finishes an episode in the time the
# episode took, which leaves nothing for the next one's overhead — the gate reads `> 1` as the
# failure and 1.0 itself as the boundary a rig should not be sitting on.
RTF_CEILING = 1.0


class Encoder(Enum):
    """The two encoder paths the condition matrix crosses.

    Named rather than free strings because the matrix is a fixed 2x2 and a run that measured
    three conditions or spelled one differently would not answer `PG-STO-001`.
    """

    SOFTWARE_SVTAV1 = "libsvtav1"
    HARDWARE_NVENC = "h264_nvenc"


@dataclass(frozen=True)
class Condition:
    """One cell of the 2x2 matrix.

    Attributes:
        encoder: Which encoder this cell exercises.
        depth_included: Whether the depth stream is part of the transcode. Depth is carried as
            its own coefficient rather than folded into the others (`02b` §6 acceptance ④): it
            is lossless 12-bit HEVC, so its bytes per frame do not scale like the colour
            streams' and an average across both would be wrong in whichever direction the mix
            happened to fall.
    """

    encoder: Encoder
    depth_included: bool

    @property
    def label(self) -> str:
        """How this cell is named in a report."""
        return f"{self.encoder.value}{'+depth' if self.depth_included else '-depth'}"


def condition_matrix() -> tuple[Condition, ...]:
    """The four conditions, in a fixed order.

    Returns:
        (tuple[Condition, ...]) Every encoder crossed with every depth setting.
    """
    return tuple(
        Condition(encoder=encoder, depth_included=depth)
        for encoder in Encoder
        for depth in (False, True)
    )


@dataclass(frozen=True)
class StreamBytes:
    """One stream's measured size and the rate it implies.

    Attributes:
        name: The stream this describes.
        bytes_written: What the transcode actually produced, in bytes.
        episode_length_s: The episode's wall-clock duration.
    """

    name: str
    bytes_written: int
    episode_length_s: float

    @property
    def bytes_per_second(self) -> float:
        """The measured coefficient for this stream."""
        return self.bytes_written / self.episode_length_s


@dataclass(frozen=True)
class RtfMeasurement:
    """One condition's result: how long the transcode took against how long the episode was.

    Attributes:
        condition: The cell of the matrix this measures.
        elapsed_s: Wall-clock seconds the transcode took.
        episode_length_s: Wall-clock seconds the episode covered.
        peak_queue_depth: The encoder queue's high-water mark during the run (acceptance ②).
        streams: Per-stream byte measurements (acceptance ③).
    """

    condition: Condition
    elapsed_s: float
    episode_length_s: float
    peak_queue_depth: int
    streams: tuple[StreamBytes, ...]

    @property
    def rtf(self) -> float:
        """Elapsed over episode length. Above `RTF_CEILING` the originals accumulate."""
        return self.elapsed_s / self.episode_length_s

    @property
    def keeps_up(self) -> bool:
        """Whether this condition transcodes at least as fast as the camera fills the disk."""
        return self.rtf <= RTF_CEILING


class RtfMeasurementError(ValueError):
    """Raised when a measurement is asked for on inputs that cannot produce a ratio."""


def measure_rtf(
    condition: Condition,
    episode_length_s: float,
    transcode: Callable[[], tuple[StreamBytes, ...]],
    peak_queue_depth: int = 0,
    clock: Callable[[], float] = time.perf_counter,
) -> RtfMeasurement:
    """Time one transcode and report it as a real-time factor.

    The clock is a parameter so a test can drive a known elapsed time without sleeping, and it
    defaults to `perf_counter` rather than `monotonic` because this measures a duration on one
    machine rather than comparing instants across one.

    Args:
        condition: Which cell of the matrix this run is.
        episode_length_s: The recorded episode's wall-clock duration; must be above zero.
        transcode: Runs the transcode and returns what each stream wrote. Called exactly once.
        peak_queue_depth: The encoder queue high-water mark observed during the run.
        clock: Monotonic seconds source, taken before and after `transcode`.

    Returns:
        (RtfMeasurement) The timing, the ratio's inputs, and the per-stream byte rates.

    Raises:
        RtfMeasurementError: When the episode length is not above zero. RTF has no meaning
            against a zero-length episode, and returning infinity would enter the gate as a
            failure caused by the denominator rather than by the encoder.
    """
    if episode_length_s <= 0.0:
        raise RtfMeasurementError(
            f"episode_length_s must be above zero, got {episode_length_s}; RTF is elapsed over "
            "episode length and a zero denominator reports the encoder for a bookkeeping error"
        )
    started = clock()
    streams = transcode()
    elapsed = clock() - started
    return RtfMeasurement(
        condition=condition,
        elapsed_s=elapsed,
        episode_length_s=episode_length_s,
        peak_queue_depth=peak_queue_depth,
        streams=streams,
    )


def coefficient_corrections(
    measured: tuple[StreamBytes, ...], declared: dict[str, float]
) -> dict[str, float]:
    """Return the declared coefficients an observation proved too small, raised to what was seen.

    Asymmetric by design (`02b` §6 acceptance ③). A declared rate ABOVE the measured one is left
    alone: over-estimating bytes per second makes a disk budget pessimistic, which costs episodes
    and nothing else. A declared rate BELOW the measured one is corrected upward, because that is
    the direction that ends a session with a full disk and originals that cannot be cleared.

    A stream the declaration does not mention is reported as a correction from zero rather than
    skipped — an unlisted stream is a coefficient of zero in every budget that reads the table,
    which is the same failure with no line to point at.

    Args:
        measured: What each stream actually wrote per second.
        declared: The bytes-per-second table in force, keyed by stream name.

    Returns:
        (dict[str, float]) Stream name to the raised coefficient, for the streams that needed
        raising. Empty when every declared rate already covered what was measured.
    """
    corrections: dict[str, float] = {}
    for stream in measured:
        observed = stream.bytes_per_second
        if observed > declared.get(stream.name, 0.0):
            corrections[stream.name] = observed
    return corrections
