"""WP-2C-02 — detection activation gate + degrade path: the single gateway for 2C real activation.

FR-SAF-030 makes collision-detection activation a function of PG-FRIC-001 PASS, and FR-SAF-001b
makes a detection loop that misses its rate a degrade with an effective-delay display. NORM-008
fixes that rate at 100 Hz and, below it, at the convergence floor `K/2` — 45 Hz at the NORM-011
gain — under which the forward-Euler residual diverges and detection is invalid rather than slow.
This package is the one place all of it is enforced as a single verdict a caller cannot route
around, and the one place the convergence relation is defined for the tree.

The public surface:

* `resolve_activation(pg_fric_001_status, band, observer_gain)` — the single gateway. Resolves
  DISABLED / ACTIVE / DEGRADED / ARCHITECTURE_REOPEN from the friction verdict, the measured band,
  and the gain.
* `measure_and_resolve(pg_fric_001_status, frames_per_cycle, fmax, observer_gain)` — measures the
  loop band (reusing WP-1-06's `resolve_detection_band`) and resolves in one call, so the cycle
  time is always measured (②).
* `gain_converges` / `assert_gain_converges` / `converging_rate_floor_hz` — the `K*dt < 2` relation
  and the rate floor it implies. WP-2C-03 calls the assert when persisting an operator-set gain,
  against a loop period its own caller passes in (`set_observer_gain(gain, detection_dt_s)`).
* `RESIDUAL_DETECTION_TARGET_HZ` / `RESIDUAL_DETECTION_TARGET_PERIOD_S` — the rate NORM-008 settles
  on, and the same operating point as a period for a caller that holds `dt` rather than `f`.
* `DetectionActivation` / `DetectionActivationMode` — the verdict and its four modes. The verdict
  carries the measured band, the enforced speed-cap scale, and the operator banner, and refuses to
  exist as a silent downgrade (③).
* `assert_activation_allowed(pg_fric_001_status)` — the API-level lock (①); raises unless PASS.
* `assert_no_silent_downgrade(activation)` — the public ③ guard a consumer calls when accepting a
  verdict.
* `scan_activation_construction(roots, exclude)` — the static single-gateway proof.
* `DetectionGateError` / `DetectionActivationRefusedError` / `SilentDowngradeError` /
  `ObserverDivergenceError` — the refusals.

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
    FORWARD_EULER_STABILITY_BOUND,
    GATE_STATE_DEGRADED_ACCEPTED,
    GATE_STATE_PASS,
    PG_FRIC_001,
    RESIDUAL_DETECTION_TARGET_HZ,
    RESIDUAL_DETECTION_TARGET_PERIOD_S,
)
from backend.detection_gate.convergence import (
    assert_gain_converges,
    converging_rate_floor_hz,
    gain_converges,
)
from backend.detection_gate.errors import (
    DetectionActivationRefusedError,
    DetectionGateError,
    ObserverDivergenceError,
    SilentDowngradeError,
)
from backend.detection_gate.staticcheck import (
    ActivationConstructionSite,
    scan_activation_construction,
)

__all__ = [
    "FORWARD_EULER_STABILITY_BOUND",
    "GATE_STATE_DEGRADED_ACCEPTED",
    "GATE_STATE_PASS",
    "PG_FRIC_001",
    "RESIDUAL_DETECTION_TARGET_HZ",
    "RESIDUAL_DETECTION_TARGET_PERIOD_S",
    "ActivationConstructionSite",
    "DetectionActivation",
    "DetectionActivationMode",
    "DetectionActivationRefusedError",
    "DetectionGateError",
    "ObserverDivergenceError",
    "SilentDowngradeError",
    "assert_activation_allowed",
    "assert_gain_converges",
    "assert_no_silent_downgrade",
    "converging_rate_floor_hz",
    "degraded_banner_text",
    "disabled_banner_text",
    "gain_converges",
    "measure_and_resolve",
    "reopen_banner_text",
    "resolve_activation",
    "scan_activation_construction",
]
