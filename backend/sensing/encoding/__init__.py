"""Two-stage encoding / transcoding worker (WP-3B-05).

`15` NFR-PRF-028 is the canon: `streaming_encoding` stays `False`, so collection
records lossless originals (RGB PNG, depth 16-bit TIFF) and a *separate* worker
transcodes them after the episode ends. The two properties this buys — the next
episode never waits on the previous transcode (`07` NFR-REC-005), and the
intermediate is lossless rather than JPEG — are the ones this package exists to hold.

The `02a` §4.1 discipline splits what runs here from what needs the rig: the parts
with no hardware dependency run and are tested here — stage-1 PNG/TIFF ingest, the
non-blocking worker with its backpressure warning, the record-start settings latch,
and the PNG-over-JPEG disk-budget correction. The one part that needs real
conditions — the production SW/HW codec matrix (`libsvtav1` / `h264_nvenc`) and its
real-time factor — is the resource-exclusive WP-3C-02 measurement (`PG-STO-001`);
the transcode codec is an injected seam here, and the offline default (`video.py`)
uses a lossless verification codec only to prove the pipe and the `NFR-CAM-007`
frame-count integrity.

`streaming_encoding=True` (the real-time-encode bypass) is the `SUPERSEDED` defect
and is refused at config construction, not left to a runtime check.
"""

from __future__ import annotations

from backend.sensing.encoding.budget import (
    IntermediateBudget,
    measured_png_jpeg_bytes,
    png_intermediate_budget,
)
from backend.sensing.encoding.config import (
    EncoderConfig,
    EncoderConfigError,
    EncoderSettings,
)
from backend.sensing.encoding.constants import (
    ENCODER_QUEUE_MAXSIZE_DEFAULT,
    NOMINAL_FPS,
    PNG_OVER_JPEG_Q90_MAX_RATIO,
    PNG_OVER_JPEG_Q90_MIN_RATIO,
    STREAMING_ENCODING_CANONICAL,
)
from backend.sensing.encoding.pipeline import EpisodeEncodingPipeline
from backend.sensing.encoding.rawstore import (
    RawEpisodeStore,
    RawIngestError,
    RawStreamRef,
    decode_frame,
    encode_frame,
)
from backend.sensing.encoding.worker import (
    BackpressureEvent,
    BackpressureWarning,
    LatencyRecorder,
    StreamTranscode,
    TranscodeJob,
    TranscodeResult,
    TranscodeWorker,
    percentile,
)

__all__ = [
    "ENCODER_QUEUE_MAXSIZE_DEFAULT",
    "NOMINAL_FPS",
    "PNG_OVER_JPEG_Q90_MAX_RATIO",
    "PNG_OVER_JPEG_Q90_MIN_RATIO",
    "STREAMING_ENCODING_CANONICAL",
    "BackpressureEvent",
    "BackpressureWarning",
    "EncoderConfig",
    "EncoderConfigError",
    "EncoderSettings",
    "EpisodeEncodingPipeline",
    "IntermediateBudget",
    "LatencyRecorder",
    "RawEpisodeStore",
    "RawIngestError",
    "RawStreamRef",
    "StreamTranscode",
    "TranscodeJob",
    "TranscodeResult",
    "TranscodeWorker",
    "decode_frame",
    "encode_frame",
    "measured_png_jpeg_bytes",
    "percentile",
    "png_intermediate_budget",
]
