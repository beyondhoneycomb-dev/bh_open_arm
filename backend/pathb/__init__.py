"""WP-2B-08 — path-B bootstrap: v2 gravity+Coriolis, friction uncompensated, detection locked.

The conditional fallback for a PG-FRIC-001 failure (02b §2.1, spec 12 §2.6 path B). It stands
ready but changes nothing about the standing rule that collision detection is off: gravity and
Coriolis are brought alive from v2 inertia, and nothing else is claimed.

The public surface:

* `PathBBootstrap(arm)` — the bootstrap. `gravity_coriolis(q, q̇)` is the v2 `qfrc_bias`
  (gravity+Coriolis, no friction) reused from WP-2B-02; `gravity(q)` is the zero-velocity term;
  `banner` and `detection` expose the two FR-SAF-030 defenses; `pg_fric_outcome` is a read-only
  FAIL_BLOCKING and `record_outcome` refuses any other value.
* `PathBBanner` — the always-visible friction-uncompensated / detection-disabled banner.
* `DetectionLock` — the code-level block: `enable()` and any activating `set_method` raise.
* `PathBError` / `DetectionLockError` — the refusals the two safety rules raise.
* `BANNER_HEADLINE` / `BANNER_DETAIL`, `DETECTION_METHOD_DISABLED`, `PG_FRIC_OUTCOME` — the fixed
  copy and enum values.
"""

from __future__ import annotations

from backend.pathb.banner import PathBBanner
from backend.pathb.bootstrap import PathBBootstrap
from backend.pathb.constants import (
    BANNER_DETAIL,
    BANNER_HEADLINE,
    DETECTION_METHOD_DISABLED,
    PG_FRIC_OUTCOME,
)
from backend.pathb.detection_lock import DetectionLock
from backend.pathb.errors import DetectionLockError, PathBError

__all__ = [
    "BANNER_DETAIL",
    "BANNER_HEADLINE",
    "DETECTION_METHOD_DISABLED",
    "PG_FRIC_OUTCOME",
    "DetectionLock",
    "DetectionLockError",
    "PathBBanner",
    "PathBBootstrap",
    "PathBError",
]
