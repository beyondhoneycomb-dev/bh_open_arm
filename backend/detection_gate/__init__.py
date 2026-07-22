"""WP-2C-02 — detection activation gate + degrade path: the single gateway for 2C real activation.

FR-SAF-030 makes collision-detection activation a function of PG-FRIC-001 PASS, and FR-SAF-001b
makes a detection loop that misses 1 kHz a degrade with an effective-delay display. This package is
the one place both rules are enforced as a single verdict a caller cannot route around.

The public surface:

* `resolve_activation(pg_fric_001_status, band)` — the single gateway. Resolves DISABLED / ACTIVE /
  DEGRADED / ARCHITECTURE_REOPEN from the friction verdict and the measured band.
* `measure_and_resolve(pg_fric_001_status, frames_per_cycle, fmax)` — measures the loop band
  (reusing WP-1-06's `resolve_detection_band`) and resolves in one call, so the cycle time is
  always measured (②).
* `DetectionActivation` / `DetectionActivationMode` — the verdict and its four modes. The verdict
  carries the measured band, the enforced speed-cap scale, and the operator banner, and refuses to
  exist as a silent downgrade (③).
* `assert_activation_allowed(pg_fric_001_status)` — the API-level lock (①); raises unless PASS.
* `assert_no_silent_downgrade(activation)` — the public ③ guard a consumer calls when accepting a
  verdict.
* `scan_activation_construction(roots, exclude)` — the static single-gateway proof.
* `DetectionGateError` / `DetectionActivationRefusedError` / `SilentDowngradeError` — the refusals.

On this host PG-FRIC-001 is hardware-deferred, so the real gate is always locked; the PASS branch is
exercised only with a synthetic status to check the logic, never to claim the gate is open.
"""

from __future__ import annotations

from backend.detection_gate.activation import (
    DetectionActivation,
    DetectionActivationMode,
    assert_activation_allowed,
    assert_no_silent_downgrade,
    measure_and_resolve,
    resolve_activation,
)
from backend.detection_gate.banner import (
    degraded_banner_text,
    disabled_banner_text,
    reopen_banner_text,
)
from backend.detection_gate.constants import (
    GATE_STATE_DEGRADED_ACCEPTED,
    GATE_STATE_PASS,
    PG_FRIC_001,
)
from backend.detection_gate.errors import (
    DetectionActivationRefusedError,
    DetectionGateError,
    SilentDowngradeError,
)
from backend.detection_gate.staticcheck import (
    ActivationConstructionSite,
    scan_activation_construction,
)

__all__ = [
    "GATE_STATE_DEGRADED_ACCEPTED",
    "GATE_STATE_PASS",
    "PG_FRIC_001",
    "ActivationConstructionSite",
    "DetectionActivation",
    "DetectionActivationMode",
    "DetectionActivationRefusedError",
    "DetectionGateError",
    "SilentDowngradeError",
    "assert_activation_allowed",
    "assert_no_silent_downgrade",
    "degraded_banner_text",
    "disabled_banner_text",
    "measure_and_resolve",
    "reopen_banner_text",
    "resolve_activation",
    "scan_activation_construction",
]
