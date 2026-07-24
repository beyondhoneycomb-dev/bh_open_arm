"""A deliberately leaky module that feeds a split-local diagnostic into the sink.

It exists only for `tests/wp4a04/test_no_leakage.py` to prove
`backend.training.normstats.staticcheck` catches the leak (WP-BOOT-03 discipline: a
checker that never fires on a real violation is worthless). It is DATA for the scanner,
never imported by product code, so its functions are never executed.
"""

from __future__ import annotations

from backend.dataset.stats import compute_diagnostic_stats
from backend.training.normstats import build_normalization_contract


def leak_via_producer_call(episodes, features):
    """A diagnostic producer's result passed straight into the contract sink."""
    return build_normalization_contract(compute_diagnostic_stats(episodes, features, "val"))


def leak_via_bound_name(episodes, features):
    """A name bound to a diagnostic producer, then passed into the sink."""
    diagnostic = compute_diagnostic_stats(episodes, features, "test")
    return build_normalization_contract(diagnostic)


def leak_via_diagnostics_attr(fitted):
    """A diagnostic read off an aggregate's `.diagnostics` and passed into the sink."""
    return build_normalization_contract(fitted.diagnostics["val"])
