"""The exceptions the GMO observer raises, all refusing rather than silently degrading.

Each names a specific contract: a wrong-width joint vector, a bad observer gain, an activation
attempt without measured torque (WP-2C-01 acceptance ②), and a static separate-process placement
(the negative branch that must be caught before the observer ever runs).
"""

from __future__ import annotations


class GmoError(Exception):
    """Base for every generalized-momentum-observer error."""


class GmoJointCountError(GmoError):
    """Raised when a joint vector is not `GMO_JOINT_COUNT` wide.

    The observer's state (momentum, gravity, Coriolis, friction, residual) is per-arm-joint, so a
    vector of the wrong width would silently misalign the joints rather than fail.
    """


class ObserverConfigError(GmoError):
    """Raised when the observer gain is not a valid per-joint set.

    The residual loop `r_dot = K*(tau_ext - r)` is only stable for a strictly positive gain, so a
    non-positive or wrong-width gain is refused at construction (WP-2C-01 acceptance ③).
    """


class TorqueFeedbackAbsentError(GmoError):
    """Raised when observer detection is activated with `use_velocity_and_torque` false.

    WP-2C-01 acceptance ②: the momentum observer's balance carries the measured joint torque
    `tau`, which the follower feedback only provides when `use_velocity_and_torque` is true. With
    it false there is no `tau_meas` — the residual would be built on an absent term — so activation
    is refused, not run on a phantom torque of zero.
    """


class SeparateProcessBindingError(GmoError):
    """Raised when the GMO source tree is placed to compute the residual outside the bus process.

    WP-2C-01 contract: the residual is computed inside the CAN-bus-owning process. A separate
    process with its own CAN socket is a second silent bind on the bus (FR-SAF-001), so a static
    reference that would spawn a process or open a bus/socket from this package is a FAIL_BLOCKING
    placement, refused before it can run.
    """
