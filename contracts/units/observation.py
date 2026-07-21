"""Per-index unit tags for the flattened `observation.state` vector.

LeRobot flattens every motor channel into one `observation.state` vector, mixing
degrees (`.pos`), degrees per second (`.vel`), and newton-metres (`.torque`) in a
single array (`10` §2.3, `16` D-8). Normalisation is element-wise, so the only way
to reason about a channel group's statistics is to know each index's unit. This
module builds that index-to-unit map from the frozen declaration, and validates
that every index carries a tag — an untagged index is one the normalisation review
cannot split by channel group.

The layout is the upstream one, not an invention: motors `joint_1..joint_7` plus
`gripper`, each contributing `.pos`/`.vel`/`.torque` in that order, arm-major for
the bimanual follower (`left_*` then `right_*`). That is 24 dimensions per arm and
48 bimanual, matching `10` §2.3 exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from contracts.units.boundary import CONTRACT_PATH
from contracts.units.tags import Deg, DegPerSec, Nm, PacketTorque, Rad, RadPerSec

# Tag class per declared unit name, so an index resolves to an actual type.
_UNIT_TYPES: dict[str, type] = {
    Deg.__name__: Deg,
    Rad.__name__: Rad,
    DegPerSec.__name__: DegPerSec,
    RadPerSec.__name__: RadPerSec,
    Nm.__name__: Nm,
    PacketTorque.__name__: PacketTorque,
}


@dataclass(frozen=True)
class ObservationChannel:
    """One index of the flattened `observation.state` vector.

    Attributes:
        index: Position in the flattened vector.
        arm: `left` or `right` for the bimanual layout; empty for single-arm.
        motor: Motor name, `joint_1..joint_7` or `gripper`.
        suffix: Channel suffix, `pos` / `vel` / `torque`.
        name: The LeRobot `names`-array entry for this index.
        unit_name: Declared unit name.
        unit: The tag type carrying this index's quantity.
    """

    index: int
    arm: str
    motor: str
    suffix: str
    name: str
    unit_name: str
    unit: type


def _load_layout(path: Path) -> dict[str, Any]:
    """Load the `observation_state` layout section from the contract YAML."""
    document: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    layout = document.get("observation_state")
    if not isinstance(layout, dict):
        raise ValueError(f"{path} declares no observation_state layout")
    return layout


def observation_state_units(
    bimanual: bool = True, path: Path = CONTRACT_PATH
) -> tuple[ObservationChannel, ...]:
    """Build the ordered index-to-unit map for the flattened observation vector.

    Args:
        bimanual: Whether to build the 48-dim bimanual layout (`left_*`/`right_*`)
            or the 24-dim single-arm layout.
        path: Location of `contracts/unit_tags.yaml`.

    Returns:
        (tuple[ObservationChannel, ...]) One channel per vector index, in the
        arm-major, motor-order, pos/vel/torque order LeRobot flattens to.

    Raises:
        ValueError: If a channel names a unit the contract does not declare.
    """
    layout = _load_layout(path)
    motors = list(layout["motors"])
    channels = list(layout["channels"])
    arms = list(layout["arms"]) if bimanual else [""]

    result: list[ObservationChannel] = []
    index = 0
    for arm in arms:
        for motor in motors:
            for channel in channels:
                suffix = str(channel["suffix"])
                unit_name = str(channel["unit"])
                if unit_name not in _UNIT_TYPES:
                    raise ValueError(
                        f"channel {motor}.{suffix} names undeclared unit '{unit_name}'"
                    )
                name = f"{arm}_{motor}.{suffix}" if arm else f"{motor}.{suffix}"
                result.append(
                    ObservationChannel(
                        index=index,
                        arm=arm,
                        motor=motor,
                        suffix=suffix,
                        name=name,
                        unit_name=unit_name,
                        unit=_UNIT_TYPES[unit_name],
                    )
                )
                index += 1
    return tuple(result)


def expected_dim(bimanual: bool = True, path: Path = CONTRACT_PATH) -> int:
    """Return the declared vector dimension for the chosen arm configuration."""
    layout = _load_layout(path)
    return int(layout["bimanual_dim"] if bimanual else layout["single_arm_dim"])
