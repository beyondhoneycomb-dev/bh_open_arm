"""The tools that can be bolted to an arm — an open registry, not a fixed pair.

Today the bench has two: the v2 pinch gripper and a fixed spatula. More are expected, so a tool
is a row in `TOOL_REGISTRY` rather than a branch in the code. Adding one is adding a row; nothing
downstream re-opens, because consumers ask a tool what it *does* (`gripper_motor`) instead of
which one it *is*.

One capability drives everything and it is electrical rather than architectural: whether CAN id
`0x08` is a motor on that arm. Addressing a motor that is not on the bus returns no error — the
frame goes out, nobody ACKs it, the transmit error counter climbs, and the controller drops to
`ERROR-PASSIVE`. Measured on this bench: sixteen unanswered frames took both channels there with
the arm unpowered. A degraded controller then affects the seven joints that *are* present, so an
absent tool motor is not a missing feature but a fault injector for the whole arm.

Mass is deliberately NOT a required field. It feeds payload registration, which gravity
compensation reads (`12` FR-SAF-036, `04` FR-MAN-033), and a wrong value shows up as a standing
offset in the collision residual. But it cannot be measured with torque off — an unactuated motor
reports zero torque whatever hangs on it — so demanding it before the torque gate would block
development on a number the rig cannot yet produce. `None` means unmeasured and travels as
`None`; consumers that need a number say so at the point they need it.
"""

from __future__ import annotations

from dataclasses import dataclass

# The gripper's CAN send id, and its index in the frozen eight-slot per-arm action layout.
GRIPPER_SEND_ID = 0x08
GRIPPER_SLOT_INDEX = 7

# Per-arm action width the frozen CTR-UNIT layout fixes. Every tool speaks this width; what
# changes between tools is what the gripper slot is allowed to carry.
ARM_SLOT_WIDTH = 8

# The seven arm joints, present on every build.
ARM_JOINT_SEND_IDS: tuple[int, ...] = (0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07)

TOOL_GRIPPER = "gripper"
TOOL_FIXED_SPATULA = "fixed_spatula"


class EndEffectorError(Exception):
    """Raised when a command names a capability the fitted tool does not have."""


@dataclass(frozen=True)
class ToolDefinition:
    """One tool that can be fitted to an arm.

    Attributes:
        tool_id: The stable identifier stored in configuration and shown in the API.
        label: Operator-facing name.
        gripper_motor: Whether this tool puts an actuated motor on CAN id `0x08`. The single
            capability that changes which ids are polled.
    """

    tool_id: str
    label: str
    gripper_motor: bool

    @property
    def motor_send_ids(self) -> tuple[int, ...]:
        """The CAN send ids present on an arm carrying this tool — never poll outside this set."""
        if self.gripper_motor:
            return (*ARM_JOINT_SEND_IDS, GRIPPER_SEND_ID)
        return ARM_JOINT_SEND_IDS


# Every tool the rig knows. Open by construction: a new tool is a new row, and a configuration
# naming one that is not here fails with the known ids listed rather than defaulting to a build.
TOOL_REGISTRY: dict[str, ToolDefinition] = {
    TOOL_GRIPPER: ToolDefinition(
        tool_id=TOOL_GRIPPER,
        label="v2 핀치 그리퍼",
        gripper_motor=True,
    ),
    TOOL_FIXED_SPATULA: ToolDefinition(
        tool_id=TOOL_FIXED_SPATULA,
        label="고정 스페츌러",
        gripper_motor=False,
    ),
}

# What an arm carries when nothing has been chosen. Deliberately the tool with no motor on
# `0x08`: defaulting to a gripper on a rig that has none polls an absent motor and degrades the
# bus silently, while defaulting the other way costs one refused command and a message. One
# default breaks the arm quietly; this one stops and says so.
DEFAULT_TOOL_ID = TOOL_FIXED_SPATULA


def tool_by_id(tool_id: str) -> ToolDefinition:
    """Look up a tool, refusing an unknown id.

    Args:
        tool_id: The stored identifier.

    Returns:
        (ToolDefinition) The registered tool.

    Raises:
        EndEffectorError: When the id is not registered. Refusing beats defaulting: the answer
            decides whether motor `0x08` gets polled, and a wrong guess degrades the bus.
    """
    tool = TOOL_REGISTRY.get(tool_id)
    if tool is None:
        known = ", ".join(sorted(TOOL_REGISTRY))
        raise EndEffectorError(f"unknown tool {tool_id!r}; registered tools are {known}")
    return tool


def registered_tools() -> tuple[ToolDefinition, ...]:
    """Every registered tool, id-sorted — what a GUI offers as choices."""
    return tuple(TOOL_REGISTRY[tool_id] for tool_id in sorted(TOOL_REGISTRY))
