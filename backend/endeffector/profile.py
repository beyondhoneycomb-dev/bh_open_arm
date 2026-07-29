"""Which end effector each arm carries, and what follows from that.

This rig ships in two end-effector builds and both stay supported:

  * `GRIPPER` — the v2 pinch gripper on CAN id `0x08`, one actuated DOF.
  * `FIXED_SPATULA` — a rigid tool bolted where the gripper was. **No motor `0x08`.**

The distinction is not cosmetic, and the reason is electrical rather than architectural.
Addressing a motor that is not on the bus produces no error return: the frame goes out, nobody
ACKs it, and the transmit error counter climbs until the controller drops to `ERROR-PASSIVE`.
That was measured on this bench — sixteen unanswered frames took both channels from
`ERROR-ACTIVE` to `ERROR-PASSIVE` with the arm unpowered. A degraded controller then affects
the seven joints that *are* present, so an absent gripper is not a missing feature but a fault
injector for the whole arm. `motor_send_ids` exists so nothing ever polls what is not there.

The action contract is NOT narrowed. `contracts/unit_tags.yaml` is `CONTRACT_FROZEN` at eight
slots per arm (`joint_1..joint_7, gripper`) and `FROZEN_ACTION_WIDTH` is 16; a spatula build
still speaks that width. What changes is the meaning of the eighth slot: on a spatula arm a
gripper command is **refused, not dropped**. Dropping it would let a policy trained on gripper
data run on a spatula rig with its grasp commands silently going nowhere, which reads as a
policy that never grasps rather than as a rig that cannot.

Mass is carried here because `12` FR-SAF-036 and `04` FR-MAN-033 register payload *including
end-effector weight*, and gravity compensation consumes that number. Swapping a gripper for a
spatula changes it, and an unchanged number shows up as a standing offset in the collision
residual — the same failure mode an unidentified friction model produces.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# One arm's motor CAN send ids with a gripper fitted (`03` FR-MOT-001, `openarm_cell.yaml`).
GRIPPER_BUILD_SEND_IDS: tuple[int, ...] = (0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08)

# The same arm with the gripper removed. J8 is absent from the bus, not merely unused.
SPATULA_BUILD_SEND_IDS: tuple[int, ...] = (0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07)

# The gripper's CAN send id and its index in the eight-slot per-arm action layout.
GRIPPER_SEND_ID = 0x08
GRIPPER_SLOT_INDEX = 7

# Per-arm action width the frozen CTR-UNIT layout fixes, gripper slot included in both builds.
ARM_SLOT_WIDTH = 8


class EndEffectorError(Exception):
    """Raised when a command names an end-effector capability the fitted build does not have."""


class EndEffector(Enum):
    """The end-effector builds this rig supports."""

    GRIPPER = "gripper"
    FIXED_SPATULA = "fixed_spatula"


@dataclass(frozen=True)
class EndEffectorProfile:
    """What one arm carries, and the facts every consumer derives from it.

    Attributes:
        end_effector: The fitted build.
        tool_mass_kg: The end effector's mass, kg, or None when it has not been weighed.
            Feeds the payload registration gravity compensation reads (`12` FR-SAF-036); None
            is carried rather than a placeholder so a consumer can refuse instead of computing
            with a number nobody measured.
    """

    end_effector: EndEffector
    tool_mass_kg: float | None

    @property
    def has_actuated_gripper(self) -> bool:
        """Whether CAN id `0x08` is a motor on this arm."""
        return self.end_effector is EndEffector.GRIPPER

    @property
    def motor_send_ids(self) -> tuple[int, ...]:
        """The CAN send ids present on this arm — never poll outside this set.

        A spatula build returns seven. Polling the eighth drives the controller toward
        `ERROR-PASSIVE`, which degrades the seven joints that do exist.
        """
        return GRIPPER_BUILD_SEND_IDS if self.has_actuated_gripper else SPATULA_BUILD_SEND_IDS

    @property
    def motor_count(self) -> int:
        """How many motors this arm has on the bus."""
        return len(self.motor_send_ids)

    def assert_gripper_command_allowed(self, value: float) -> None:
        """Refuse a gripper command on an arm that has no gripper.

        A zero command is admitted on both builds: the frozen action layout always carries the
        slot, and a caller filling it with zero is stating "no gripper action", not requesting
        one. Anything else on a spatula arm is a request the hardware cannot serve.

        Args:
            value: The commanded gripper slot value.

        Raises:
            EndEffectorError: When a non-zero gripper command reaches a spatula arm.
        """
        if self.has_actuated_gripper or value == 0.0:
            return
        raise EndEffectorError(
            f"gripper command {value} on a {self.end_effector.value} arm: this build has no "
            f"motor {GRIPPER_SEND_ID:#04x}. The command is refused rather than dropped — a "
            "silently discarded grasp reads as a policy that never grasps."
        )


def gripper_build(tool_mass_kg: float | None = None) -> EndEffectorProfile:
    """The pinch-gripper build."""
    return EndEffectorProfile(end_effector=EndEffector.GRIPPER, tool_mass_kg=tool_mass_kg)


def spatula_build(tool_mass_kg: float | None = None) -> EndEffectorProfile:
    """The fixed-spatula build: rigid tool, no motor `0x08`."""
    return EndEffectorProfile(end_effector=EndEffector.FIXED_SPATULA, tool_mass_kg=tool_mass_kg)
