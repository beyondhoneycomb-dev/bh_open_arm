"""The cycle-time histogram collector — full distributions, never summary-only.

`02a` WP-0C-06 acceptance ⑥ forbids publishing p50/p95/p99 alone: the artifact must
carry the whole distribution, because a percentile triple hides the bimodal tail a
GIL stall produces and makes the `a`-vs-`b` comparison (03 §5.1a) impossible. So a
`CycleTimeHistogram` keeps every raw cycle-time sample and can render a complete
binned histogram; the percentile summary it also offers is a convenience for a human
reader, explicitly not a substitute for the full data.

Samples are wall-clock cycle times in seconds — the time between one control-loop
deadline wakeup and the next, which is what inflates when a load thread holds the GIL
across the victim's wakeup.
"""

from __future__ import annotations

from typing import Any

import numpy as np

# The full histogram is rendered at 50 microsecond resolution. Fine enough to show a
# GIL-stall shoulder a few switch-intervals out from the mode, coarse enough that the
# published bin list stays readable. This bins the artifact's histogram only; the raw
# samples are kept at full precision regardless.
_HISTOGRAM_BIN_WIDTH_SEC = 50e-6

_PERCENTILES = (50.0, 95.0, 99.0, 99.9)


class CycleTimeHistogram:
    """Every cycle-time sample from one measured condition, plus full-distribution views.

    Ownership: holds its own copy of the sample array; callers may not mutate it after
    construction, which keeps a published artifact's numbers stable.
    """

    def __init__(self, samples: np.ndarray) -> None:
        """Take an immutable copy of the cycle-time samples.

        Args:
            samples: Cycle times in seconds. Copied and frozen against later writes.
        """
        self._samples = np.array(samples, dtype=np.float64)
        self._samples.setflags(write=False)

    @property
    def samples(self) -> np.ndarray:
        """The raw cycle-time samples in seconds (read-only)."""
        return self._samples

    @property
    def count(self) -> int:
        """How many samples were collected."""
        return int(self._samples.size)

    def overrun_rate(self, period_sec: float, tolerance: float = 0.0) -> float:
        """Fraction of cycles whose wall time exceeded the target period.

        This is the quantity `03` §5.1a's pass line reads (main-path overrun ≤ 0.1%),
        but the harness only *computes* it — it pins no numeric verdict (acceptance ⑧).
        The `tolerance` band lifts the threshold to `period * (1 + tolerance)` so the
        unavoidable `time.sleep` oversleep floor (tens of microseconds) is not counted
        as an overrun; a real GIL stall is milliseconds and clears any small band. The
        tolerance is recorded in the artifact, never hidden.

        Args:
            period_sec: The target cycle period, `1 / target_hz`.
            tolerance: Fractional slack above the period before a cycle counts as an
                overrun.

        Returns:
            (float) Overrun rate in `[0, 1]`, or 0.0 when there are no samples.
        """
        if self._samples.size == 0:
            return 0.0
        threshold = period_sec * (1.0 + tolerance)
        return float(np.mean(self._samples > threshold))

    def summary(self) -> dict[str, float]:
        """Percentile/mean summary — a convenience view, never the whole artifact.

        Returns:
            (dict[str, float]) `min`, `mean`, `max` and the p50/p95/p99/p99.9
            percentiles, all in seconds. Empty-safe: zeros when there are no samples.
        """
        if self._samples.size == 0:
            return {"count": 0.0, "min": 0.0, "mean": 0.0, "max": 0.0}
        summary: dict[str, float] = {
            "count": float(self._samples.size),
            "min": float(self._samples.min()),
            "mean": float(self._samples.mean()),
            "max": float(self._samples.max()),
        }
        for percentile in _PERCENTILES:
            summary[f"p{percentile:g}"] = float(np.percentile(self._samples, percentile))
        return summary

    def binned(self, bin_width_sec: float = _HISTOGRAM_BIN_WIDTH_SEC) -> dict[str, Any]:
        """Render the complete binned histogram over all samples.

        Args:
            bin_width_sec: Bin width in seconds.

        Returns:
            (dict[str, Any]) `bin_width_sec`, the left `edges` of each bin, and the
            per-bin `counts`. Every sample falls in exactly one bin — this is the
            full distribution acceptance ⑥ requires, not a summary of it.
        """
        if self._samples.size == 0:
            return {"bin_width_sec": bin_width_sec, "edges": [], "counts": []}
        low = float(self._samples.min())
        high = float(self._samples.max())
        bin_count = max(1, int(np.ceil((high - low) / bin_width_sec)) + 1)
        edges = low + bin_width_sec * np.arange(bin_count + 1)
        counts, _ = np.histogram(self._samples, bins=edges)
        return {
            "bin_width_sec": bin_width_sec,
            "edges": [float(edge) for edge in edges[:-1]],
            "counts": [int(count) for count in counts],
        }

    def as_record(self) -> dict[str, Any]:
        """Serialize the full distribution for the artifact.

        Returns:
            (dict[str, Any]) `sample_count`, the full `raw_samples`, the full
            `histogram`, and the convenience `summary`. `raw_samples` and `histogram`
            are both present so the artifact refusal guard (acceptance ⑥) can confirm
            the distribution was published whole.
        """
        return {
            "sample_count": self.count,
            "raw_samples": [float(sample) for sample in self._samples],
            "histogram": self.binned(),
            "summary": self.summary(),
        }
