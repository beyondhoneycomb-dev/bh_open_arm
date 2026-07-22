"""The observer's activation gate: reuse the WP-1-06 method selector, add the torque-feedback bar.

WP-2C-01 does not introduce a second detection-method enum. The four-value selector
(`MOMENTUM_OBSERVER` / `TORQUE_RESIDUAL` / `CURRENT_LIMIT` / `DISABLED`, default
`MOMENTUM_OBSERVER`) and two of its preconditions already live in `backend.safety_bringup`
(WP-1-06): the acceleration-limit precondition for residual methods (FR-SAF-014) and the
friction-established gate (`gmo_active_default`, FR-SAF-030). This module re-exports that selector
and composes those gates with the one precondition WP-2C-01 adds:

  * Acceptance ② — measured torque must be present. The momentum observer's balance carries
    `tau_meas`, which the follower feedback only provides when `use_velocity_and_torque` is true.
    With it false there is no torque term (and the recorder's `build_dataset_frame` would raise a
    KeyError on the missing key), so observer activation is refused, not run on a phantom zero.

`observer_detection_active` is the single activation entry point: it raises on the hard refusals
(accel limit off, torque absent) and otherwise reports whether GMO detection is actually live —
which, until PG-FRIC-001 establishes friction, is False even though the method names the observer.
"""

from __future__ import annotations

from pathlib import Path

from backend.gmo.errors import TorqueFeedbackAbsentError
from backend.safety_bringup.detection import (
    DEFAULT_DETECTION_METHOD,
    RESIDUAL_BASED_METHODS,
    DetectionMethod,
    ResidualDetectionRefusedError,
    enable_residual_detection,
    gmo_active_default,
)

__all__ = [
    "DEFAULT_DETECTION_METHOD",
    "RESIDUAL_BASED_METHODS",
    "DetectionMethod",
    "ResidualDetectionRefusedError",
    "assert_torque_feedback_available",
    "observer_detection_active",
]


def assert_torque_feedback_available(use_velocity_and_torque: bool) -> None:
    """Refuse observer activation when measured torque is absent (acceptance ②).

    Args:
        use_velocity_and_torque: The single follower/leader switch. Only when true does the
            feedback frame carry `tau_meas`.

    Raises:
        TorqueFeedbackAbsentError: If `use_velocity_and_torque` is false.
    """
    if not use_velocity_and_torque:
        raise TorqueFeedbackAbsentError(
            "momentum observer activation needs measured torque; use_velocity_and_torque is false "
            "so tau_meas is absent and activation is refused (WP-2C-01 acceptance ②)"
        )


def observer_detection_active(
    method: DetectionMethod,
    use_velocity_and_torque: bool,
    accel_limit_active: bool,
    friction_yaml_path: Path,
) -> bool:
    """Return whether GMO detection is live, refusing the hard preconditions first.

    The order is: is the momentum observer even the selected method; then the two refusals (accel
    limit, torque feedback); then the friction-established gate that decides live-or-not.

    Args:
        method: The selected detection method.
        use_velocity_and_torque: Whether the feedback frame carries measured torque.
        accel_limit_active: Whether the joint acceleration limit is active (FR-SAF-014).
        friction_yaml_path: Path to the friction descriptor; non-empty means friction established.

    Returns:
        (bool) True only when the observer is selected, its preconditions hold, and friction is
        established. False when the observer is not the selected method, or friction is not yet
        established (the default-off state until PG-FRIC-001).

    Raises:
        ResidualDetectionRefusedError: If a residual method is selected with the accel limit off.
        TorqueFeedbackAbsentError: If activation is attempted without measured torque.
    """
    if method not in RESIDUAL_BASED_METHODS:
        return False
    enable_residual_detection(method, accel_limit_active)
    assert_torque_feedback_available(use_velocity_and_torque)
    return gmo_active_default(friction_yaml_path)
