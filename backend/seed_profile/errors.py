"""The error types WP-2B-10 raises to keep the v1 seed out of the v2 runtime (FR-SAF-031/067).

All subclass `ValueError`, matching the WP-2B-01/2B-02 convention: a caller already guarding
asset handling for `ValueError` keeps working, while a caller that wants to tell a seed-isolation
refusal apart from an unrelated value error can catch these specifically. Each refusal is loud
and carries its reason, because the failure this package exists to stop — a v1 value entering the
v2 runtime — is dangerous precisely when it happens *silently*.
"""

from __future__ import annotations


class SeedProfileError(ValueError):
    """Base type for every seed-isolation refusal."""


class SeedWriteRefusedError(SeedProfileError):
    """A write to the read-only seed profile was refused (FR-SAF-031).

    The v1 seed is the frozen origin the v2 asset is derived from; rewriting it in place would
    destroy the only immutable reference the promotion diff is measured against. The forward
    path is an explicit v1->v2 promotion into a new v2 asset, never an edit of the seed.
    """


class PromotionNotApprovedError(SeedProfileError):
    """A v1->v2 promotion was activated without an explicit approval of its report (FR-SAF-067).

    Activation binds to the digest of the per-joint relative-error report an operator saw, so a
    blank or mismatched approval — one that did not acknowledge this exact report — is refused
    rather than silently activated.
    """


class SeedContaminationError(SeedProfileError):
    """A v1-generation value reached the v2 runtime gate — asset contamination (FR-SAF-067).

    This is the FAIL_BLOCKING failure of `02b` WP-2B-10: a `robot_version != "2.0"` asset loaded
    into the v2 runtime is a v1 model masquerading as a v2 one. The strict provenance gate refuses
    it here so it never loads silently; the only asset that passes is one promoted to a genuine v2
    stamp.
    """
