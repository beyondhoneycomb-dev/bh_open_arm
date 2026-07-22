"""WP-2C-01 — the generalized-momentum-observer (GMO) collision-detection residual.

    r(t) = K { p - integral( tau + C_hat^T*q_dot - g_hat - F_hat + r ) dxi - p(0) }

The residual `r` estimates the unmodelled joint torque; a nonzero `r_i` isolates joint i, which on
a collision is the contact torque. The observer reuses rather than re-derives its model terms:
gravity `g_hat` and the Coriolis term from `backend.gravity` (WP-2B-02), friction `F_hat` from
`backend.friction` (WP-2B-07), and the four-value detection-method selector from
`backend.safety_bringup` (WP-1-06). The one dynamics quantity no reused package exposes — the mass
matrix `M(q)` behind the momentum `p` — is added here.

Two contracts hold the package together:

  * The residual is computed *inside the CAN-bus-owning process* (`single_process` proves it
    statically): a separate process with its own CAN socket is a second silent bind (FR-SAF-001)
    and is FAIL_BLOCKING.
  * Activation is refused without measured torque (`selector`, acceptance ②) and — until
    PG-FRIC-001 establishes friction — GMO detection stays disabled by default even though the
    method names the observer. This host builds and tests all machinery; on-hardware calibration
    and timing are deferred.

Public surface:

  * `MomentumObserver` — the residual with a per-joint independent gain `K` (acceptance ③).
  * `GmoModelTerms` / `MassMatrix` / `FrictionFeedforward` — the reused-plus-added model terms.
  * `isolate_joints` / `Isolation` — the "which joint" report against per-joint thresholds.
  * `observer_detection_active` / `assert_torque_feedback_available` / `DetectionMethod` — the
    activation gate (re-exporting the WP-1-06 selector, not redefining it).
  * `inject_external_force` / `SyntheticInjection` — the offline synthetic-injection harness.
  * `assert_single_process_binding` / `scan_tree` — the single-process static proof.
"""

from __future__ import annotations

from backend.gmo.constants import (
    DEFAULT_OBSERVER_GAIN,
    GMO_JOINT_COUNT,
    NOMINAL_DETECTION_DT_S,
)
from backend.gmo.errors import (
    GmoError,
    GmoJointCountError,
    ObserverConfigError,
    SeparateProcessBindingError,
    TorqueFeedbackAbsentError,
)
from backend.gmo.friction_term import FrictionFeedforward
from backend.gmo.isolation import Isolation, isolate_joints
from backend.gmo.mass import MassMatrix
from backend.gmo.model import GmoModelTerms
from backend.gmo.observer import MomentumObserver
from backend.gmo.selector import (
    DEFAULT_DETECTION_METHOD,
    RESIDUAL_BASED_METHODS,
    DetectionMethod,
    ResidualDetectionRefusedError,
    assert_torque_feedback_available,
    observer_detection_active,
)
from backend.gmo.single_process import (
    Finding,
    assert_single_process_binding,
    check_source,
    scan_tree,
)
from backend.gmo.synthetic import (
    SyntheticInjection,
    default_trajectory,
    inject_external_force,
    momentum_consistent_torque,
)

__all__ = [
    "DEFAULT_DETECTION_METHOD",
    "DEFAULT_OBSERVER_GAIN",
    "GMO_JOINT_COUNT",
    "NOMINAL_DETECTION_DT_S",
    "RESIDUAL_BASED_METHODS",
    "DetectionMethod",
    "Finding",
    "FrictionFeedforward",
    "GmoError",
    "GmoJointCountError",
    "GmoModelTerms",
    "Isolation",
    "MassMatrix",
    "MomentumObserver",
    "ObserverConfigError",
    "ResidualDetectionRefusedError",
    "SeparateProcessBindingError",
    "SyntheticInjection",
    "TorqueFeedbackAbsentError",
    "assert_single_process_binding",
    "assert_torque_feedback_available",
    "check_source",
    "default_trajectory",
    "inject_external_force",
    "isolate_joints",
    "momentum_consistent_torque",
    "observer_detection_active",
    "scan_tree",
]
