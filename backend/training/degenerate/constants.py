"""Named constants for the WP-4A-03 degenerate-channel band (`02c` §1.3).

Two families live here and they must not be confused:

- the LeRobot normalization epsilon, a *fact* about the upstream contract
  (`normalize_processor.py`, `FR-TRN-067`), and
- the DERIVATION-HARNESS separation criteria, which decide whether a channel-std
  distribution is bimodal enough to place a threshold — meta-parameters of the
  harness, NOT the degeneracy threshold itself. `02c` §1.3 is explicit that the
  plan does not pin σ_min/δ_min: the threshold is derived from the real per-channel
  distribution, and until Wave 3C real data lands there is none. So no σ_min value
  appears in this file — a target here would be exactly the "measure-before-target"
  violation the σ_min-derivation block forbids.
"""

from __future__ import annotations

from backend.dataset.stats.constants import MOMENT_METRIC_KEYS
from backend.training.preflight import REQUIRED_QUANTILE_KEYS

# The epsilon LeRobot's normalizer floors the denominator with (`FR-TRN-067`,
# `normalize_processor.py:97, 349-395`: `denom = std + eps`,
# `torch.where(denom == 0, eps, denom)`). This is the N-1 ledger resolution: `10`
# wins over `08` — the eps floor IS applied, and its being applied is what silently
# amplifies a degenerate channel rather than raising. We do not change it (we
# cannot, and `FR-TRN-069` forbids per-group rescaling); we read it to estimate the
# amplification a degenerate channel suffers.
LEROBOT_NORMALIZE_EPS = 1e-8

# The `meta/stats.json` metric-key spellings the per-mode statistic reads, tied to
# their upstream source so a rename there is caught here. `std`/`min`/`max` are the
# `compute_stats` moment keys (`MOMENT_METRIC_KEYS`); `q01`/`q99` are the quantile
# keys preflight already keys on (`REQUIRED_QUANTILE_KEYS`), reused so the two bands
# cannot spell the same quantile differently.
STD_KEY = "std"
MIN_KEY = "min"
MAX_KEY = "max"
Q01_KEY, Q99_KEY = REQUIRED_QUANTILE_KEYS

# Guard against a silent drift of the moment-key spellings: if `compute_stats`
# renames `std`/`min`/`max`, this band must fail to import rather than read a
# missing key as "not degenerate".
_MOMENT_KEYS_PRESENT = {STD_KEY, MIN_KEY, MAX_KEY} <= set(MOMENT_METRIC_KEYS)
if not _MOMENT_KEYS_PRESENT:  # pragma: no cover - a drift tripwire, not a runtime branch
    raise ImportError(
        f"degenerate detector expects moment keys {{{STD_KEY},{MIN_KEY},{MAX_KEY}}} "
        f"in compute_stats MOMENT_METRIC_KEYS {MOMENT_METRIC_KEYS}"
    )

# --- Derivation-harness separation criteria (NOT the degeneracy threshold) ------

# The number of log-scale bins the channel-statistic histogram is rendered with.
# A display/inspection resolution, not a decision boundary.
HISTOGRAM_BIN_COUNT = 20

# The valley between the degenerate cluster and the normal cluster must span at
# least this many decades on a log10 scale to count as a real separation. This is
# the criterion for "are there two clusters", not the value of σ_min — σ_min is
# placed at the valley midpoint only once this is satisfied.
MIN_SEPARATION_DECADES = 2.0

# The widest log-gap must dominate the rest by this factor to be read as a single
# valley rather than a merely uneven-but-unimodal spread. Guards against declaring
# separation on a distribution that has no genuine gap.
DOMINANT_GAP_RATIO = 3.0

# Below this many channels a histogram cannot show a distribution, so the harness
# refuses to auto-derive and defers to the show-every-channel fallback.
MIN_CHANNELS_FOR_DERIVATION = 4

# `02c` §1.3 SHAPE-IM(3): the std-distribution harness MUST be re-run when Wave 3C
# real-collected data lands, because the fixture distribution is not the real one.
# The harness stamps this onto every derivation so a threshold derived from
# fixtures cannot be mistaken for one validated against real data.
NEEDS_REAL_DATA_RERUN = True
