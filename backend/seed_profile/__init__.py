"""WP-2B-10 — seed-profile isolation: the v1 seed is read-only and reaches v2 only by approval.

This package keeps the v1 dynamics seed from ever silently becoming a v2 runtime value
(FR-SAF-031/067). It sits on top of WP-2B-01's converter and provenance gate and adds the three
things that turn "a v1 asset exists" into "a v1 asset cannot leak":

* `SeedProfile` / `SeedProfileStore` — the seed is loaded read-only and every write is refused
  (`SeedWriteRefusedError`). The seed is v1 by construction; a v2-stamped 'seed' is refused, and the
  in-memory profile is immutable at three levels (frozen dataclass, read-only payload view, deep
  copies out).
* `build_promotion_report` / `promote` — the explicit v1->v2 path. The report shows per-joint
  relative error (joint2's +pi/2 shift is the large-error fingerprint); activation requires an
  `Approval` bound by digest to that exact report, so nothing activates without an operator
  having seen the diff (`PromotionNotApprovedError`).
* `load_into_v2_runtime` — the single v2-runtime gate. A v1-stamped asset is refused as
  contamination (`SeedContaminationError`), the FAIL_BLOCKING condition of `02b` WP-2B-10.
"""

from __future__ import annotations

from backend.seed_profile.constants import SEED_PROFILE_NAME, SEED_ROBOT_VERSION
from backend.seed_profile.errors import (
    PromotionNotApprovedError,
    SeedContaminationError,
    SeedProfileError,
    SeedWriteRefusedError,
)
from backend.seed_profile.profile import SeedProfile
from backend.seed_profile.promotion import (
    Approval,
    JointRelativeError,
    PromotedProfile,
    PromotionReport,
    build_promotion_report,
    promote,
)
from backend.seed_profile.runtime import load_into_v2_runtime
from backend.seed_profile.store import SeedProfileStore

__all__ = [
    "SEED_PROFILE_NAME",
    "SEED_ROBOT_VERSION",
    "Approval",
    "JointRelativeError",
    "PromotedProfile",
    "PromotionNotApprovedError",
    "PromotionReport",
    "SeedContaminationError",
    "SeedProfile",
    "SeedProfileError",
    "SeedProfileStore",
    "SeedWriteRefusedError",
    "build_promotion_report",
    "load_into_v2_runtime",
    "promote",
]
