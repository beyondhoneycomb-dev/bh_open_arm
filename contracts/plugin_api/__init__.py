"""CTR-PLUG@v1 plugin-API freeze surface (WP-1-01, 01 FR-SYS-014 / 09 FR-SIM-097).

WP-1-01 confirms the unified robot-plugin API on the hardware axis: LeRobot is
extended only through its third-party plugin mechanism, LeRobot proper is unedited,
and CTR-PLUG@v1 stays registered and lockable. This package holds the machine
statements of that surface:

- `convention` — the distribution-name convention and the no-fork check. Pure
  stdlib, so the light lane can import it.
- `freeze` — CTR-PLUG@v1 registration re-confirmation against the freeze authority.
  Light lane (reads JSON only).
- `surface` — the frozen Robot ABC surface, derived from the shared ABC.
- `extension` — the LeRobot extension mechanism and its zero-edit proofs.

`surface` and `extension` import the robot stack, so — like `contracts.plugin` — they
are NOT re-exported here; import them explicitly to keep `import contracts.plugin_api`
free of LeRobot.
"""

from __future__ import annotations

from contracts.plugin_api.convention import (
    OPENARM_ROBOT_DIST,
    PLUGIN_DIST_PREFIXES,
    PluginConventionError,
    forks_no_lerobot,
    is_convention_compliant,
    require_convention,
)
from contracts.plugin_api.freeze import CONTRACT_ID, OWNER_WP, Registration, registration

__all__ = [
    "CONTRACT_ID",
    "OPENARM_ROBOT_DIST",
    "OWNER_WP",
    "PLUGIN_DIST_PREFIXES",
    "PluginConventionError",
    "Registration",
    "forks_no_lerobot",
    "is_convention_compliant",
    "registration",
    "require_convention",
]
