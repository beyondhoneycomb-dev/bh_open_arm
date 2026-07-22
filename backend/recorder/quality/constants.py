"""Named layout and magnitude constants for the recorder quality/store band (WP-3B-12, `02b` §5.2).

The values here are on-disk layout names, byte magnitudes and the minimum sample
counts a finite-difference metric needs — not acceptance targets. The quality-gate
thresholds are deliberately absent: `02b` §5.2 WP-3B-12 ⑥ fixes them as `[결정필요]`,
to be measured then regression-locked, and forbids adopting ALOHA's 84% success-rate
figure because that was measured on different hardware. A caller supplies thresholds
to `report.evaluate`; this module names none.
"""

from __future__ import annotations

# Byte magnitudes. The disk watermark is an operational store-safety floor — the free
# space below which recording must safe-store and stop — not a quality gate. Named
# here, overridable per `DiskWatch`, and provisional rather than a measured target.
BYTES_PER_KIBIBYTE = 1024
BYTES_PER_MEBIBYTE = BYTES_PER_KIBIBYTE * BYTES_PER_KIBIBYTE
DEFAULT_MIN_FREE_BYTES = 512 * BYTES_PER_MEBIBYTE

# The episode sidecar lives beside the dataset under meta/, never inside the parquet
# or mp4 tree: a label or quality edit must not re-serialise a recorded frame (`02b`
# §5.2 WP-3B-12 ①). One JSON file per episode, joined to the dataset by episode index.
QUALITY_SUBDIR = "meta/quality"
QUARANTINE_SUBDIR = "meta/quarantine"
SIDECAR_PREFIX = "episode_"
SIDECAR_SUFFIX = ".json"

# A footerless parquet is the crash signature: the Parquet footer and its trailing
# "PAR1" magic are written last, so their absence means the writer died mid-episode
# (`02b` §5.2 WP-3B-12 ⑤). Detection reads the trailing magic without opening the file.
PARQUET_MAGIC = b"PAR1"
PARQUET_MAGIC_LEN = len(PARQUET_MAGIC)
RECOVERED_SUFFIX = ".recovered"

# Finite-difference sample floors. A rate needs two timestamps to form one interval;
# jerk is the third derivative, so it is undefined below four samples.
MIN_SAMPLES_FOR_RATE = 2
MIN_SAMPLES_FOR_JERK = 4

# The unit a jerk magnitude carries, recorded in the report so a reader never has to
# infer it from the position unit (`CTR-REC@v1` `.pos` = degrees).
JERK_UNIT = "deg/s^3"
