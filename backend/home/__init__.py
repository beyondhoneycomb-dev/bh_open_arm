"""Home profile, home return, and session-end stop posture (WP-2D-07).

The home is a configurable profile whose default is the FR-MAN-047-adopted
`[0, 0, 0, π/2, 0, 0, 0, 0]` — never the `J4 = 0` mechanical hardstop. A home return shows
its target before running and executes only after a pre-verify passes; the pre-verify is
the reused WP-2C-08 collision preflight (via `HomePreflight`), and the target EE preview is
FK over the reused WP-2D-01 `KinematicFrames`. The session-end stop posture rides the same
guarded path. The operator J4=0-hardstop visual confirm is Human-judgment and stays
SKIP-with-reason plus a re-verification hook (`backend.home.decision`).
"""

from __future__ import annotations

from backend.home.decision import (
    HOME_DECISION,
    DeferredVisualConfirm,
    HomeDecision,
    VisualConfirmRecord,
    deferred_visual_confirm,
    reverify_visual_confirm,
)
from backend.home.homereturn import (
    HomeLeg,
    HomePreview,
    HomeReturn,
    HomeReturnBlockedError,
    HomeReturnPlan,
    build_home_preview,
)
from backend.home.preverify import HomePreflight
from backend.home.profile import (
    HomeProfile,
    HomeProfileError,
    HomeProfileRegistry,
    JointLimitMargin,
    default_home_profile,
    default_registry,
    session_stop_profile,
    validate_home_profile,
)

__all__ = [
    "HOME_DECISION",
    "DeferredVisualConfirm",
    "HomeDecision",
    "HomeLeg",
    "HomePreflight",
    "HomePreview",
    "HomeProfile",
    "HomeProfileError",
    "HomeProfileRegistry",
    "HomeReturn",
    "HomeReturnBlockedError",
    "HomeReturnPlan",
    "JointLimitMargin",
    "VisualConfirmRecord",
    "build_home_preview",
    "default_home_profile",
    "default_registry",
    "deferred_visual_confirm",
    "reverify_visual_confirm",
    "session_stop_profile",
    "validate_home_profile",
]
