"""Clamp-canon selection for the dry-run — refuse to run until one is chosen.

`09` FR-SIM-031 (position) and FR-SIM-032 (velocity) both require the limit canon
to be *explicitly selected* from real candidates, and FR-SIM-132 requires the
dry-run to **refuse to run** when a canon is unselected. That refusal is the whole
point: a dry-run with no declared position/velocity canon would validate a
trajectory against nothing and wave it through, which is worse than not running.

So the two canons default to ``UNSELECTED`` and a ``ClampCanon`` carrying either
``UNSELECTED`` raises at construction — there is no way to hold an un-chosen canon
and still get a runnable dry-run. Position offers URDF / MJCF / LeRobot
(FR-SIM-031); MJCF is wired to the live model's ``jnt_range`` (the sim's real
limit source), and the other two require a caller-supplied table because their
values live in coordinate systems this WP does not transcribe — selecting one
without its table is refused, not silently emptied. Velocity offers the two
per-joint candidate tables `09` FR-SIM-032 lists (URDF, ``openarm_control``);
Isaac Lab's two-value table is not a full per-joint mapping and is left out rather
than fabricated into seven values.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

import mujoco

from sim.dryrun.limits import (
    openarm_control_velocity_limits_rad_s,
    urdf_velocity_limits_rad_s,
)
from sim.dryrun.topology import arm_joint_addresses


class PositionCanon(Enum):
    """The position-limit canon (`09` FR-SIM-031); ``UNSELECTED`` refuses to run."""

    UNSELECTED = "unselected"
    MJCF = "mjcf"
    URDF = "urdf"
    LEROBOT = "lerobot"


class VelocityCanon(Enum):
    """The velocity-limit canon (`09` FR-SIM-032); ``UNSELECTED`` refuses to run."""

    UNSELECTED = "unselected"
    URDF = "urdf"
    OPENARM_CONTROL = "openarm_control"


class ClampCanonUnselectedError(RuntimeError):
    """Raised when a dry-run is attempted with a position/velocity canon unchosen.

    `09` FR-SIM-132: a dry-run must refuse to run until the clamp canon is selected.
    """


@dataclass(frozen=True)
class ClampCanon:
    """The selected position and velocity canons for a dry-run.

    Construction refuses any ``UNSELECTED`` member, so a ``ClampCanon`` instance is
    proof that both canons were explicitly chosen (`09` FR-SIM-031/032/132).

    Attributes:
        position: The chosen position-limit canon.
        velocity: The chosen velocity-limit canon.
        position_table_rad: Required only when ``position`` is URDF or LeRobot: the
            per-joint ``(lower, upper)`` bounds in radians for that canon.
    """

    position: PositionCanon = PositionCanon.UNSELECTED
    velocity: VelocityCanon = VelocityCanon.UNSELECTED
    position_table_rad: Mapping[str, tuple[float, float]] | None = None

    def __post_init__(self) -> None:
        """Refuse any unselected canon, or a table-requiring canon without its table."""
        if self.position is PositionCanon.UNSELECTED:
            raise ClampCanonUnselectedError(
                "position clamp canon is unselected; the dry-run refuses to run (09 FR-SIM-031/132)"
            )
        if self.velocity is VelocityCanon.UNSELECTED:
            raise ClampCanonUnselectedError(
                "velocity clamp canon is unselected; the dry-run refuses to run (09 FR-SIM-032/132)"
            )
        if (
            self.position in (PositionCanon.URDF, PositionCanon.LEROBOT)
            and self.position_table_rad is None
        ):
            raise ClampCanonUnselectedError(
                f"position canon {self.position.value} needs an explicit per-joint "
                "table (its values are not transcribed here); refusing to run"
            )

    def resolve_position_bounds(self, model: mujoco.MjModel) -> dict[str, tuple[float, float]]:
        """Return per-joint position bounds (radians) for the selected canon.

        Args:
            model: The compiled model (read for the MJCF ``jnt_range`` when the
                MJCF canon is selected).

        Returns:
            (dict[str, tuple[float, float]]) Motor key to ``(lower, upper)`` radians.
        """
        if self.position is PositionCanon.MJCF:
            return {
                address.motor_key: (
                    float(model.jnt_range[address.jnt_id][0]),
                    float(model.jnt_range[address.jnt_id][1]),
                )
                for address in arm_joint_addresses(model)
            }
        # URDF / LeRobot: the caller supplied the table (enforced in __post_init__).
        assert self.position_table_rad is not None
        return dict(self.position_table_rad)

    def resolve_velocity_limits(self) -> dict[str, float]:
        """Return per-joint velocity bounds (rad/s) for the selected canon.

        Returns:
            (dict[str, float]) Motor key to symmetric speed bound in rad/s.
        """
        if self.velocity is VelocityCanon.URDF:
            return urdf_velocity_limits_rad_s()
        return openarm_control_velocity_limits_rad_s()
