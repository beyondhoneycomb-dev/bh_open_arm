"""The joint-limit virtual-wall repulsion torque added to tau during Freedrive (WP-2D-04).

`04` FR-MAN-036: Freedrive must enforce the joint limits even though it runs in torque mode,
where LeRobot's position clipping is void (`torque_mode`). Within 5 deg of a limit a virtual
wall pushes the joint back toward the interior with a torque added to the MIT `tau`, so a
hand-guide meets a soft wall before the mechanical hardstop. The wall's ceiling is bounded
by the joint's URDF effort limit — a wall that pushes harder than the actuator is rated for
is refused at construction, not clamped in flight (`RepulsionEffortExceededError`).

Two reuse boundaries hold this module to one source of truth. The soft limits come from
`sim.ik.limits.arm_soft_limits` — LeRobot's own defaults, the same numbers IK constrains
against — never a second copy invented here. The per-joint effort ceiling is the canonical
`URDF_EFFORT_LIMIT_NM` table, and the final per-joint cap is applied through the sanctioned
`contracts.units.clamp_torque`, so the effort bound is enforced by the one torque clamp the
codebase owns.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from backend.freedrive_walls.constants import (
    ARM_JOINT_COUNT,
    DEFAULT_REPULSION_EFFORT_FRACTION,
    MAX_REPULSION_EFFORT_FRACTION,
    NEAR_LIMIT_BAND_RAD,
    URDF_EFFORT_LIMIT_NM,
)
from backend.freedrive_walls.errors import FreedriveConfigError, RepulsionEffortExceededError
from contracts.units.tags import Nm
from contracts.units.torque import clamp_torque


@dataclass(frozen=True)
class JointWall:
    """One joint's virtual-wall envelope: its soft range and its repulsion ceiling.

    The ceiling (`max_repulsion_nm`) is validated against the URDF effort at construction:
    a wall may not be built to push past the actuator's rated effort, which is the
    `02b` §4.2 WP-2D-04 FAIL_BLOCKING branch. Angles are radians in the v2 model convention.

    Attributes:
        lower_rad: Lower soft limit, radians.
        upper_rad: Upper soft limit, radians.
        effort_nm: The joint's URDF effort limit, Nm — the ceiling the cap may not exceed.
        max_repulsion_nm: The repulsion torque magnitude at (and past) the hardstop, Nm.
    """

    lower_rad: float
    upper_rad: float
    effort_nm: float
    max_repulsion_nm: float

    def __post_init__(self) -> None:
        """Refuse an inverted range, a non-positive effort, or a negative cap.

        The cap-exceeds-effort FAIL_BLOCKING check is not here: it is applied in
        `JointLimitRepulsion.__init__`, where the joint index is known and can name the
        offending joint. This validates only the single-wall shape invariants.

        Raises:
            FreedriveConfigError: If the range is not strictly increasing, the effort is
                not positive, or the cap is negative.
        """
        if not self.lower_rad < self.upper_rad:
            raise FreedriveConfigError(
                f"joint range must be increasing, got [{self.lower_rad}, {self.upper_rad}]"
            )
        if not self.effort_nm > 0.0:
            raise FreedriveConfigError(f"effort must be positive, got {self.effort_nm}")
        if self.max_repulsion_nm < 0.0:
            raise FreedriveConfigError(
                f"repulsion cap must be non-negative, got {self.max_repulsion_nm}"
            )


class JointLimitRepulsion:
    """The per-joint virtual-wall repulsion torque field for one arm (`04` FR-MAN-036).

    Ownership/threading: immutable after construction; `repulsion_torque` is a pure function
    of the joint angles, so one instance serves any number of ticks on any thread. It holds
    only the per-joint walls and the shared band width.
    """

    def __init__(self, walls: Sequence[JointWall], band_rad: float = NEAR_LIMIT_BAND_RAD) -> None:
        """Bind the field to its per-joint walls and the near-limit band.

        Args:
            walls: One wall per arm joint, in joint order.
            band_rad: The distance from a limit within which the wall engages, radians.

        Raises:
            FreedriveConfigError: If no walls are given or the band is not positive.
            RepulsionEffortExceededError: If any wall's repulsion cap exceeds its URDF
                effort — the `02b` §4.2 WP-2D-04 FAIL_BLOCKING branch.
        """
        if not walls:
            raise FreedriveConfigError("at least one joint wall is required")
        if not band_rad > 0.0:
            raise FreedriveConfigError(f"band must be positive, got {band_rad}")
        for index, wall in enumerate(walls):
            if wall.max_repulsion_nm > wall.effort_nm:
                raise RepulsionEffortExceededError(index, wall.max_repulsion_nm, wall.effort_nm)
        self._walls = tuple(walls)
        self._band_rad = band_rad

    @property
    def count(self) -> int:
        """The number of joints this field covers."""
        return len(self._walls)

    @property
    def band_rad(self) -> float:
        """The near-limit band width the wall engages within, radians."""
        return self._band_rad

    def lower_bounds(self) -> tuple[float, ...]:
        """The per-joint lower soft limits, radians (the limit-violation detector's input)."""
        return tuple(wall.lower_rad for wall in self._walls)

    def upper_bounds(self) -> tuple[float, ...]:
        """The per-joint upper soft limits, radians (the limit-violation detector's input)."""
        return tuple(wall.upper_rad for wall in self._walls)

    def repulsion_torque(self, q: Sequence[float]) -> tuple[Nm, ...]:
        """Return the per-joint virtual-wall repulsion torque to add to tau.

        A joint deeper than `band_rad` from both limits contributes zero. Within the band
        the torque ramps linearly from zero at the band edge to `max_repulsion_nm` at the
        limit, and saturates there for any over-limit angle. Near the upper limit the torque
        is negative (toward the interior); near the lower limit, positive. The final value is
        clamped to the joint's cap through `clamp_torque`, so the effort bound holds even if
        both walls of a very tight joint engage at once.

        Args:
            q: Per-joint angles this tick, radians, in joint order.

        Returns:
            (tuple[Nm, ...]) The per-joint repulsion torque, one entry per joint.

        Raises:
            FreedriveConfigError: If `q` is not the joint count wide.
        """
        if len(q) != self.count:
            raise FreedriveConfigError(f"q must be {self.count} wide, got {len(q)}")
        out: list[Nm] = []
        for angle, wall in zip(q, self._walls, strict=True):
            torque = 0.0
            distance_to_upper = wall.upper_rad - angle
            distance_to_lower = angle - wall.lower_rad
            if distance_to_upper < self._band_rad:
                torque -= self._ramp(distance_to_upper) * wall.max_repulsion_nm
            if distance_to_lower < self._band_rad:
                torque += self._ramp(distance_to_lower) * wall.max_repulsion_nm
            out.append(clamp_torque(Nm(torque), Nm(wall.max_repulsion_nm)))
        return tuple(out)

    def _ramp(self, distance_to_limit: float) -> float:
        """Return the 0..1 penetration ramp for a distance to a limit.

        Zero at (or beyond) the band edge, one at (or past) the limit; linear between.

        Args:
            distance_to_limit: Signed distance to the limit, radians — negative past it.

        Returns:
            (float) The ramp factor in [0, 1].
        """
        penetration = (self._band_rad - distance_to_limit) / self._band_rad
        return max(0.0, min(1.0, penetration))


def build_arm_repulsion(
    side: str,
    fraction: float = DEFAULT_REPULSION_EFFORT_FRACTION,
    band_rad: float = NEAR_LIMIT_BAND_RAD,
) -> JointLimitRepulsion:
    """Build one arm's repulsion field from the reused soft limits and effort table.

    The soft limits are `sim.ik.limits.arm_soft_limits` — LeRobot's own defaults — and the
    effort ceilings are the canonical `URDF_EFFORT_LIMIT_NM`; the cap for each joint is
    `fraction` of that effort. Neither number is invented here.

    Args:
        side: ``"right"`` or ``"left"``.
        fraction: The share of each joint's URDF effort the wall may spend at the hardstop;
            must be in (0, 1].
        band_rad: The near-limit band, radians.

    Returns:
        (JointLimitRepulsion) The arm's virtual-wall repulsion field.

    Raises:
        FreedriveConfigError: If `fraction` is outside (0, 1].
        RepulsionEffortExceededError: If a resulting cap exceeds the joint effort.
    """
    if not 0.0 < fraction <= MAX_REPULSION_EFFORT_FRACTION:
        raise FreedriveConfigError(
            f"repulsion effort fraction must be in (0, {MAX_REPULSION_EFFORT_FRACTION}], "
            f"got {fraction}"
        )
    # Imported here, not at module load, so the field carries no import-time dependency on
    # the robot stack; only a caller that actually builds a real arm pulls LeRobot in — the
    # same lazy boundary sim.ik.limits itself keeps.
    from sim.ik.limits import arm_soft_limits

    limits = arm_soft_limits(side)
    if len(limits) != ARM_JOINT_COUNT:
        raise FreedriveConfigError(
            f"expected {ARM_JOINT_COUNT} arm limits for side {side!r}, got {len(limits)}"
        )
    walls = tuple(
        JointWall(
            lower_rad=limit.lower_rad.value,
            upper_rad=limit.upper_rad.value,
            effort_nm=effort,
            max_repulsion_nm=effort * fraction,
        )
        for limit, effort in zip(limits, URDF_EFFORT_LIMIT_NM, strict=True)
    )
    return JointLimitRepulsion(walls, band_rad)
