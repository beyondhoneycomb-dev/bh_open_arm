"""Per-process RSS slope monitor — leak detection (`15` NFR-PRF-044).

NFR-PRF-044: a process whose resident set grows without bound is leaking. A single high RSS
reading proves nothing (a large model is not a leak); the *slope* over time is the signal. So
this monitor samples `VmRSS` from `/proc/<pid>/status` and fits a least-squares line; a slope
above the threshold, over enough samples, is a leak.

`/proc` is read directly rather than through `psutil` so the monitor carries no third-party
dependency and works on any Linux host, robot or dev desktop alike.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ops.telemetry.constants import (
    BYTES_PER_KIB,
    RSS_LEAK_SLOPE_BYTES_PER_S,
    RSS_MIN_SAMPLES_FOR_SLOPE,
)


class RssReadError(RuntimeError):
    """`VmRSS` could not be read for a pid (process gone, or field absent)."""


def read_rss_bytes(pid: int) -> int:
    """Read a process's resident set size in bytes from `/proc/<pid>/status`.

    Args:
        pid: The process to read.

    Returns:
        (int) Resident set size in bytes.

    Raises:
        RssReadError: If the status file or the `VmRSS` field is unavailable.
    """
    status = Path(f"/proc/{pid}/status")
    try:
        text = status.read_text(encoding="utf-8")
    except OSError as error:
        raise RssReadError(f"cannot read {status}: {error}") from error
    for line in text.splitlines():
        if line.startswith("VmRSS:"):
            # Format: "VmRSS:\t   6888 kB" — the kernel reports KiB.
            kib = int(line.split()[1])
            return kib * BYTES_PER_KIB
    raise RssReadError(f"no VmRSS field for pid {pid}")


@dataclass(frozen=True)
class RssSample:
    """One resident-set reading.

    Attributes:
        t: Monotonic seconds at the reading.
        rss_bytes: Resident set size in bytes.
    """

    t: float
    rss_bytes: int


class RssSlopeMonitor:
    """Accumulates RSS samples and reports the least-squares growth slope.

    Ownership/threading: single consumer. One monitor per watched process; the sampler feeds
    it and asks `leaking` after enough samples have accrued.
    """

    def __init__(
        self,
        threshold_bytes_per_s: float = RSS_LEAK_SLOPE_BYTES_PER_S,
        min_samples: int = RSS_MIN_SAMPLES_FOR_SLOPE,
    ) -> None:
        self.m_threshold = threshold_bytes_per_s
        self.m_min_samples = min_samples
        self.m_samples: list[RssSample] = []

    def add(self, t: float, rss_bytes: int) -> None:
        """Record one RSS sample.

        Args:
            t: Monotonic seconds at the reading.
            rss_bytes: Resident set size in bytes.
        """
        self.m_samples.append(RssSample(t=t, rss_bytes=rss_bytes))

    def add_reading(self, t: float, pid: int) -> None:
        """Read a process's RSS now and record it at time `t`.

        Args:
            t: Monotonic seconds to stamp the reading with.
            pid: The process to read.
        """
        self.add(t, read_rss_bytes(pid))

    def slope_bytes_per_s(self) -> float | None:
        """Fit a least-squares line to the samples and return its slope.

        Returns:
            (float | None) Bytes-per-second growth, or None when there are too few samples
            or every sample shares one timestamp (an undefined slope).
        """
        samples = self.m_samples
        count = len(samples)
        if count < self.m_min_samples:
            return None
        mean_t = sum(sample.t for sample in samples) / count
        mean_rss = sum(sample.rss_bytes for sample in samples) / count
        variance_t = sum((sample.t - mean_t) ** 2 for sample in samples)
        if variance_t == 0.0:
            return None
        covariance = sum((sample.t - mean_t) * (sample.rss_bytes - mean_rss) for sample in samples)
        return covariance / variance_t

    def leaking(self) -> bool:
        """Report whether the fitted slope exceeds the leak threshold.

        Returns:
            (bool) True when a slope is defined and above the threshold.
        """
        slope = self.slope_bytes_per_s()
        return slope is not None and slope > self.m_threshold
