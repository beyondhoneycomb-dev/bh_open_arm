"""Named reference values for the two-stage encoding pipeline (`NFR-PRF-028`).

Every literal the pipeline decides on lives here once. The canonical facts these
names carry are LeRobot upstream defaults the OpenArm design pins deliberately
(`06` §2.8, `07` NFR-REC-005, `15` NFR-PRF-028): `streaming_encoding` stays
`False` so collection records lossless originals and transcodes after the episode,
and the intermediate is PNG (depth 16-bit TIFF), never JPEG. They are named — not
inlined — so the one place the design commits to them is auditable, and so a
consumer states the value by reference rather than restating a bare literal.
"""

from __future__ import annotations

# The `streaming_encoding` canon (`15` NFR-PRF-028, `configs/dataset.py:67`). It is
# fixed `False`, not merely defaulted: collection writes lossless originals and a
# separate worker transcodes after the episode. A `True` bypass is the `SUPERSEDED`
# defect (`02b` §6.2 WP-3B-05 negative branch), refused at config construction.
STREAMING_ENCODING_CANONICAL = False

# The encoder backpressure threshold (`configs/dataset.py`: `encoder_queue_maxsize
# = 30`), roughly one second of outstanding transcode work at 30 fps. Crossing it
# raises a warning rather than blocking the next episode (`07` NFR-REC-005): the
# originals are already on disk, so falling behind grows the disk (F14 / R-20), it
# does not corrupt a recording.
ENCODER_QUEUE_MAXSIZE_DEFAULT = 30

# The nominal capture rate the one-second backpressure buffer is sized against
# (`06`: `fps = 30`). Named so the buffer-seconds relationship is derivable, not a
# coincidence of two bare 30s.
NOMINAL_FPS = 30

# The upstream image-writer thread count per camera (`configs/dataset.py`:
# `num_image_writer_threads_per_camera = 4`). Stage-1 ingest streams originals to
# disk off the capture thread; this is the writer fan-out that keeps grab
# non-blocking. Recorded for provenance — this package encodes frames, it does not
# own the writer pool (that is the recorder embed, WP-3B-11).
IMAGE_WRITER_THREADS_PER_CAMERA = 4

# The stage-1 original file patterns (`06` §2.8, LeRobot `datasets/utils.py:82-98`):
# lossless PNG for RGB, 16-bit TIFF for depth. The six-digit zero-padded frame index
# is the sidecar/dataset join key (`CTR-CAP@v1` `frame_index`), so the on-disk order
# is the record order.
IMAGE_FILE_PATTERN = "frame-{frame_index:06d}.png"
DEPTH_FILE_PATTERN = "frame-{frame_index:06d}.tiff"

# PNG is lossless at any compression level; the level only trades size for CPU. It
# is pinned so a re-run of stage-1 ingest produces byte-identical originals, which
# keeps the transcode-integrity hash (`NFR-CAM-007`) reproducible.
PNG_COMPRESSION_LEVEL = 3

# The JPEG quality the disk budget is compared against. LeRobot's intermediate is
# NOT JPEG; q90 is only the baseline the `15` NFR-PRF-026/028 budget was originally
# written for, kept here to compute the correction factor below.
JPEG_Q90_QUALITY = 90

# The lossless-PNG-over-JPEG-q90 size band (`15` NFR-PRF-028, `06` §2.8: a lossless
# PNG original is 3-8x the size of the same frame at JPEG q90). The intermediate
# disk budget and the record-block thresholds must be raised by a factor in this
# band; the exact factor on real imagery is an M-5 real-fixture measurement
# (`15` NFR-PRF-026 note), so this is a band, not a point.
PNG_OVER_JPEG_Q90_MIN_RATIO = 3.0
PNG_OVER_JPEG_Q90_MAX_RATIO = 8.0

# The percentiles `07` NFR-REC-005 records for both the `save_episode()` return
# latency and the batch-transcode completion latency.
PERCENTILE_P50 = 50.0
PERCENTILE_P95 = 95.0
