"""Grasp-force monitoring by the absolute value of gripper.torque, per-unit only.

FR-SAF-024b: grasp force is watched not by a residual but by |gripper.torque|, and it
is never shown in a physical force unit — the per-unit-to-force constant is undetermined
(spec 12 §5-Q14) and no load cell is used, so a physical figure would assert a
calibration we lack. Everything here works in and displays the per-unit domain [0, 1]
(inherited from WP-2A-08). A magnitude at or above the force cap raises the over-grip
alarm; the cap is a per-unit configuration, not a measured force.

Config validation and live classification are split on purpose: the thresholds are
validated to the per-unit domain at construction (a physical value is refused, as in
WP-2A-08), while `classify` never refuses a live reading — a hot magnitude must still
grade as an over-grip alarm rather than crash the monitor.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from backend.gripper_endpoint.constants import TORQUE_PU_MAX, TORQUE_PU_MIN
from backend.temp_gripper.constants import (
    GRASP_CONTACT_THRESHOLD_PU_DEFAULT,
    GRASP_FORCE_CAP_PU_DEFAULT,
)
from backend.temp_gripper.errors import TempGripperConfigError
from backend.temp_gripper.labels import GRASP_FORCE_VALUE_LABEL, GRASP_STATE_LABELS


class GraspState(Enum):
    """The grasp state a per-unit |torque| magnitude falls into."""

    RELEASED = "released"
    GRASPING = "grasping"
    OVER_GRIP = "over_grip"


@dataclass(frozen=True)
class GraspVerdict:
    """A classified grasp reading — per-unit, never a physical force.

    Attributes:
        torque_pu_abs: |gripper.torque| in the per-unit domain [0, 1].
        state: The grasp state the magnitude falls into.
        over_grip: Whether the magnitude reached the over-grip alarm cap.
    """

    torque_pu_abs: float
    state: GraspState
    over_grip: bool


class GraspForceMonitor:
    """Classifies |gripper.torque| against a per-unit contact threshold and force cap.

    Ownership/threading: immutable after construction; a single caller drives
    `classify`/`format_status` per feedback cycle. It reads a per-unit torque and
    returns a per-unit verdict — no bus access, no physical-unit conversion.
    """

    def __init__(
        self,
        contact_threshold_pu: float = GRASP_CONTACT_THRESHOLD_PU_DEFAULT,
        force_cap_pu: float = GRASP_FORCE_CAP_PU_DEFAULT,
    ) -> None:
        """Validate the two per-unit thresholds and store them.

        Args:
            contact_threshold_pu: |torque_pu| below this is no contact.
            force_cap_pu: |torque_pu| at or above this is the over-grip alarm.

        Raises:
            TempGripperConfigError: If either threshold leaves the per-unit domain
                [0, 1] (a physical-unit intrusion) or the contact threshold is not below
                the force cap.
        """
        for name, value in (
            ("contact threshold", contact_threshold_pu),
            ("force cap", force_cap_pu),
        ):
            if not TORQUE_PU_MIN <= value <= TORQUE_PU_MAX:
                raise TempGripperConfigError(
                    f"grasp {name} must be per-unit in [{TORQUE_PU_MIN}, {TORQUE_PU_MAX}], "
                    f"got {value}; a physical force unit is not accepted"
                )
        if not contact_threshold_pu < force_cap_pu:
            raise TempGripperConfigError(
                f"grasp contact threshold {contact_threshold_pu} must be below the force cap "
                f"{force_cap_pu}"
            )
        self._contact_threshold_pu = contact_threshold_pu
        self._force_cap_pu = force_cap_pu

    def classify(self, torque_pu: float) -> GraspVerdict:
        """Grade one per-unit torque reading by its absolute value.

        Args:
            torque_pu: The observed gripper.torque, per-unit; its sign is a direction,
                so the threshold is applied to the absolute value.

        Returns:
            (GraspVerdict) The magnitude, its grasp state, and the over-grip flag.
        """
        magnitude = abs(torque_pu)
        if magnitude >= self._force_cap_pu:
            return GraspVerdict(magnitude, GraspState.OVER_GRIP, True)
        if magnitude >= self._contact_threshold_pu:
            return GraspVerdict(magnitude, GraspState.GRASPING, False)
        return GraspVerdict(magnitude, GraspState.RELEASED, False)

    def format_status(self, torque_pu: float) -> str:
        """Render a user-facing grasp-force line — per-unit magnitude and state, no unit.

        Args:
            torque_pu: The observed gripper.torque, per-unit.

        Returns:
            (str) A per-unit grasp-force status line carrying no physical force unit.
        """
        verdict = self.classify(torque_pu)
        state_label = GRASP_STATE_LABELS[verdict.state.value]
        return f"{GRASP_FORCE_VALUE_LABEL}: {verdict.torque_pu_abs:.3f} [{state_label}]"
