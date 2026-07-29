"""What one arm carries, and what follows from it.

A profile is a registered tool plus what has been measured about this particular one. The tool
says what the arm *can* do; the measurement says what is known about the thing bolted on.

Mass is optional and stays optional. It feeds payload registration, which gravity compensation
reads (`12` FR-SAF-036, `04` FR-MAN-033), and a wrong value shows up as a standing offset in the
collision residual. But **it cannot be measured with torque off** — an unactuated motor reports
zero torque whatever hangs on it — so it cannot exist before the torque gate. Requiring it would
block every step that has nothing to do with mass. So `None` travels as `None`, and the one
consumer that genuinely needs a number (`payload_mass_kg`) is the only place that refuses.

The action contract is not narrowed. `contracts/unit_tags.yaml` is `CONTRACT_FROZEN` at eight
slots per arm and `FROZEN_ACTION_WIDTH` is 16; every tool speaks that width. What changes is the
meaning of the eighth slot: on an arm whose tool has no gripper motor, a gripper command is
**refused, not dropped**. Dropping it would let a policy trained on gripper data run with its
grasp commands going nowhere, which reads as a policy that never grasps rather than as a rig that
cannot.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from backend.endeffector.tools import (
    DEFAULT_TOOL_ID,
    GRIPPER_SEND_ID,
    TOOL_FIXED_SPATULA,
    TOOL_GRIPPER,
    EndEffectorError,
    ToolDefinition,
    tool_by_id,
)


@dataclass(frozen=True)
class EndEffectorProfile:
    """One arm's fitted tool, plus what has been measured about it.

    Attributes:
        tool: The registered tool.
        tool_mass_kg: The fitted tool's mass, kg, or None when it has not been measured. None is
            carried rather than a placeholder so nothing computes with a number nobody measured.
    """

    tool: ToolDefinition
    tool_mass_kg: float | None

    @property
    def tool_id(self) -> str:
        """The stored identifier for this arm's tool."""
        return self.tool.tool_id

    @property
    def has_actuated_gripper(self) -> bool:
        """Whether CAN id `0x08` is a motor on this arm."""
        return self.tool.gripper_motor

    @property
    def motor_send_ids(self) -> tuple[int, ...]:
        """The CAN send ids present on this arm — never poll outside this set.

        Polling an absent motor drives the controller toward `ERROR-PASSIVE`, which degrades the
        seven joints that do exist.
        """
        return self.tool.motor_send_ids

    @property
    def motor_count(self) -> int:
        """How many motors this arm has on the bus."""
        return len(self.motor_send_ids)

    @property
    def mass_is_measured(self) -> bool:
        """Whether this tool's mass has been measured.

        False blocks nothing on its own. It is a fact to display and to gate the one computation
        that needs the number, not a precondition for using the arm.
        """
        return self.tool_mass_kg is not None

    def payload_mass_kg(self) -> float:
        """Return the mass for payload registration, refusing when it was never measured.

        This is the only place an unmeasured mass is an error, and the refusal is here rather
        than at load time because this is where the number would silently become wrong: gravity
        compensation subtracts a payload torque, and subtracting the wrong one puts a constant
        offset on the collision residual that looks like a mis-tuned threshold.

        Raises:
            EndEffectorError: When the mass has not been measured.
        """
        if self.tool_mass_kg is None:
            raise EndEffectorError(
                f"{self.tool_id} mass has not been measured; register it or run the tool-mass "
                "calibration. Gravity compensation cannot subtract a payload nobody weighed — "
                "the error would appear as a standing collision-residual offset, not as a "
                "missing value."
            )
        return self.tool_mass_kg

    def with_measured_mass(self, mass_kg: float) -> EndEffectorProfile:
        """Return this profile with a measured mass attached.

        Args:
            mass_kg: The measured mass, kg. Must be positive — a fitted tool has mass, and an
                unmeasured one is None rather than zero.

        Raises:
            EndEffectorError: On a non-positive mass.
        """
        if mass_kg <= 0.0:
            raise EndEffectorError(
                f"measured tool mass {mass_kg} kg is not positive; an unmeasured tool is None"
            )
        return replace(self, tool_mass_kg=float(mass_kg))

    def assert_gripper_command_allowed(self, value: float) -> None:
        """Refuse a gripper command on an arm whose tool has no gripper motor.

        A zero command is admitted on every tool: the frozen action layout always carries the
        slot, and filling it with zero states "no gripper action" rather than requesting one.

        Args:
            value: The commanded gripper slot value.

        Raises:
            EndEffectorError: When a non-zero gripper command reaches a tool without the motor.
        """
        if self.has_actuated_gripper or value == 0.0:
            return
        raise EndEffectorError(
            f"gripper command {value} on a {self.tool_id} arm: this tool has no motor "
            f"{GRIPPER_SEND_ID:#04x}. Refused rather than dropped — a silently discarded grasp "
            "reads as a policy that never grasps."
        )


def profile_for(tool_id: str, tool_mass_kg: float | None = None) -> EndEffectorProfile:
    """Build a profile for a registered tool id.

    Raises:
        EndEffectorError: When the tool id is not registered.
    """
    return EndEffectorProfile(tool=tool_by_id(tool_id), tool_mass_kg=tool_mass_kg)


def default_profile() -> EndEffectorProfile:
    """The profile an arm carries before anything is chosen — the tool with no `0x08` motor."""
    return profile_for(DEFAULT_TOOL_ID)


def gripper_build(tool_mass_kg: float | None = None) -> EndEffectorProfile:
    """The pinch-gripper build."""
    return profile_for(TOOL_GRIPPER, tool_mass_kg)


def spatula_build(tool_mass_kg: float | None = None) -> EndEffectorProfile:
    """The fixed-spatula build: rigid tool, no motor `0x08`."""
    return profile_for(TOOL_FIXED_SPATULA, tool_mass_kg)
