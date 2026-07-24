"""Named constants for the WP-4A-04 normalization-stats contract (`02c` §1.4).

The three split names and the train-only fit split are imported from the committed
WP-3D-03 band rather than restated, so the contract's `fit_split` is the same token
the fit refuses to move off (`backend.dataset.stats.fit.fit_normalization_stats`).
`REAL_INFERENCE` is the fourth `applied_to` target — real-robot inference — which is
not a dataset split, so it is named here and not among the committed `SPLIT_NAMES`.

`QUANTILE_BINS` is LeRobot's `RunningQuantileStats(num_quantile_bins=5000)` default:
the quantiles a fitted table carries are a histogram estimate over 5000 bins, not
exact values (`FR-DAT-029`). The contract records that fact so a consumer never
mistakes an approximate `q01`/`q99` for an exact one; the exact-vs-approx deviation
is measured by `deviation.contract_quantile_deviation_report`, never assumed.
"""

from __future__ import annotations

from backend.dataset.stats.constants import TEST_SPLIT, TRAIN_SPLIT, VAL_SPLIT

# The split normalization statistics are fit on, and the only split a fit accepts.
# `02c` §1.4 / `FR-TRN-024`: fit on train, apply the SAME statistics everywhere.
FIT_SPLIT = TRAIN_SPLIT

# Real-robot inference — the fourth target the train statistics apply to, alongside
# the three dataset splits. Not a dataset split, so it is not in `SPLIT_NAMES`.
REAL_INFERENCE = "real"

# Every context the ONE train-fit statistic is applied to (`FR-TRN-024`): the three
# dataset splits plus real inference. val/test/real never re-fit — a per-split re-fit
# is validation leakage and forbidden (`FR-DAT-031`).
APPLIED_TO = (TRAIN_SPLIT, VAL_SPLIT, TEST_SPLIT, REAL_INFERENCE)

# The contract always declares its quantiles approximate: `compute_stats` estimates
# them from a histogram, never exactly (`FR-DAT-029`).
QUANTILE_APPROX = True

# LeRobot's `RunningQuantileStats` histogram bin count (`num_quantile_bins=5000`),
# the resolution the approximate quantiles are estimated at (`FR-DAT-029`).
QUANTILE_BINS = 5000
