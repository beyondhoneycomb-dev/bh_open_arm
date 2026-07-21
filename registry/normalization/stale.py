"""Staleness propagation for a normalization hash bump.

`02a` §1.5 WP-N1-04 ③ and the `05` §5.2 propagation table: a one-row ledger change
bumps the issued hash, and every un-integrated descendant that referenced the old
hash goes stale, with a cancel signal for the work that has not been merged.

This does not re-implement propagation. The transitive descendant closure already
lives in `registry/state/closure.py` (the same walk `05` P-2 uses for a gate flip),
and cancellability already lives in `registry/state/store.py` (integrated work is
excluded by `05` §5.2 P-4). A hash bump is just another trigger fed through that
machinery, so this module supplies the trigger token and joins the two halves.
"""

from __future__ import annotations

from registry.state.closure import RegistryGraph, StaleClosure, descendant_closure
from registry.state.store import StateStore

# The staleness trigger a hash bump injects. Downstream records declare it on their
# `stale_on` axis exactly as they declare `env_hash:CHANGED` for an environment
# rebuild (`02a` WP-ENV-04) — the closure walk treats every trigger the same.
NORMALIZATION_TRIGGER = "normalization_hash:CHANGED"


def hash_bump_closure(graph: RegistryGraph) -> StaleClosure:
    """Enumerate every descendant a normalization hash bump invalidates.

    Args:
        graph: Registry graph over the stale and downstream axes.

    Returns:
        (StaleClosure) The transitive closure seeded by the hash-bump trigger.
    """
    return descendant_closure(graph, NORMALIZATION_TRIGGER)


def cancel_signals(closure: StaleClosure, store: StateStore) -> list[str]:
    """Select the invalidated packages whose un-integrated work must be cancelled.

    Integrated work is excluded on purpose: it is stamped stale and reverted by a
    named WP, never cancelled (`05` §5.2 P-4).

    Args:
        closure: The descendant closure of a hash bump.
        store: The execution state store.

    Returns:
        (list[str]) Work package ids to send a cancel signal, sorted.
    """
    return store.cancellable(sorted(closure.wps))
