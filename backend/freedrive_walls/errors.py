"""Errors the Freedrive virtual-wall band raises, one distinct type per failure mode.

Two of these are the `02b` §4.2 WP-2D-04 negative branches, and they are hard errors, not
silent clamps: a repulsion whose cap exceeds the joint's URDF effort
(`RepulsionEffortExceededError`) and a Freedrive detection policy that switches off a
hardware-fault or limit-violation detector (`DetectionRetainedError`) are both
`FAIL_BLOCKING`. Raising rather than clamping keeps the caller from believing an
out-of-envelope wall or a blind detector was accepted.
"""

from __future__ import annotations

from collections.abc import Sequence


class FreedriveWallError(Exception):
    """Base class for every Freedrive virtual-wall failure."""


class FreedriveConfigError(FreedriveWallError, ValueError):
    """Raised when a wall or detection configuration is internally malformed.

    Wrong vector widths, a non-positive band, or an inverted joint range — shape
    faults that precede any physics, distinct from the two acceptance-level
    FAIL_BLOCKING branches below.
    """


class RepulsionEffortExceededError(FreedriveWallError):
    """Raised when a joint's repulsion cap exceeds its URDF effort limit (FAIL_BLOCKING).

    `02b` §4.2 WP-2D-04: the repulsion torque ceiling must stay within the URDF effort
    limit; a wall configured to push harder than the actuator's rated effort is refused,
    never clamped, because a saturating wall is the failure the acceptance forbids.

    Attributes:
        joint_index: Zero-based arm joint whose cap is out of envelope.
        cap_nm: The requested repulsion cap, Nm.
        effort_nm: The joint's URDF effort limit, Nm.
    """

    def __init__(self, joint_index: int, cap_nm: float, effort_nm: float) -> None:
        """Build the error naming the joint and the two torques.

        Args:
            joint_index: Zero-based arm joint index.
            cap_nm: The requested repulsion cap, Nm.
            effort_nm: The joint's URDF effort limit, Nm.
        """
        super().__init__(
            f"joint {joint_index}: repulsion cap {cap_nm} Nm exceeds the URDF effort limit "
            f"{effort_nm} Nm; the virtual-wall torque must stay within effort "
            "(02b §4.2 WP-2D-04, FAIL_BLOCKING)"
        )
        self.joint_index = joint_index
        self.cap_nm = cap_nm
        self.effort_nm = effort_nm


class DetectionRetainedError(FreedriveWallError):
    """Raised when Freedrive would switch off a retained detector (FAIL_BLOCKING).

    `04` FR-MAN-037 / `02b` §4.2 WP-2D-04: Freedrive may suppress only the residual
    (GMO) trip, because a hand-guide force is itself an external residual. Motor
    hardware faults (ERR nibble, temperature, comm loss) and limit-violation detection
    must stay. Disabling any of those is the detection-fully-off branch — detection off
    down to the hardware fault — and it is refused.

    Attributes:
        disabled: The retained detector kinds a config tried to switch off.
    """

    def __init__(self, disabled: Sequence[object]) -> None:
        """Build the error naming the retained detectors that were switched off.

        Args:
            disabled: The retained detector kinds the config disabled.
        """
        names = ", ".join(str(kind) for kind in disabled)
        super().__init__(
            f"Freedrive may not disable retained detection: {names}. Only the residual (GMO) "
            "trip may be suppressed; hardware faults and limit violations stay active "
            "(04 FR-MAN-037, 02b §4.2 WP-2D-04, FAIL_BLOCKING)"
        )
        self.disabled = tuple(disabled)
