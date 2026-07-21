"""Physical-quantity tag types — the root of system-wide unit safety (CTR-UNIT@v1).

A unit is a type, not a comment. `openarm_control` speaks radians and LeRobot
speaks degrees (`01` FR-SYS-016), so a missing conversion is not an exception at
runtime — it is a command that is wrong by a factor of 57.3 and executes anyway.
The only defence that holds *at all times*, rather than at a gate, is the type
system: a value carrying an angle in degrees must not be assignable where radians
are expected, and mixing the two in arithmetic must not type-check.

Each tag is a distinct frozen wrapper, not an alias:

- `typing.NewType` gives nominal identity but leaves the base type's operators in
  place, so `Deg(1) + Rad(1)` would silently return a `float`. That defeats the
  one property this contract exists to guarantee.
- A frozen dataclass owns its operators. Same-unit addition and comparison are
  defined and typed to the same unit; cross-unit arithmetic has no overload and
  is therefore a static type error, not a runtime surprise.

Crossing between units is possible only through the named conversion functions in
`contracts.units.conversions`. There is no implicit path: no shared base makes two
units mutually assignable, no `__float__` leaks the raw value into arithmetic, and
the wrapped `value` is a plain `float` that a conversion function reads explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class Deg:
    """An angle in degrees. LeRobot joint space and MJCF authoring are degrees."""

    value: float

    def __add__(self, other: Deg) -> Deg:
        """Add another degree angle. No overload accepts a different unit."""
        return Deg(self.value + other.value)

    def __sub__(self, other: Deg) -> Deg:
        """Subtract another degree angle."""
        return Deg(self.value - other.value)

    def scaled(self, factor: float) -> Deg:
        """Scale by a dimensionless factor, staying in degrees."""
        return Deg(self.value * factor)


@dataclass(frozen=True, order=True)
class Rad:
    """An angle in radians. `openarm_control`, IK, and CAN joint space are radians."""

    value: float

    def __add__(self, other: Rad) -> Rad:
        """Add another radian angle. No overload accepts a different unit."""
        return Rad(self.value + other.value)

    def __sub__(self, other: Rad) -> Rad:
        """Subtract another radian angle."""
        return Rad(self.value - other.value)

    def scaled(self, factor: float) -> Rad:
        """Scale by a dimensionless factor, staying in radians."""
        return Rad(self.value * factor)


@dataclass(frozen=True, order=True)
class DegPerSec:
    """An angular velocity in degrees per second (LeRobot `.vel` channel)."""

    value: float

    def __add__(self, other: DegPerSec) -> DegPerSec:
        """Add another degrees-per-second velocity."""
        return DegPerSec(self.value + other.value)

    def __sub__(self, other: DegPerSec) -> DegPerSec:
        """Subtract another degrees-per-second velocity."""
        return DegPerSec(self.value - other.value)

    def scaled(self, factor: float) -> DegPerSec:
        """Scale by a dimensionless factor, staying in degrees per second."""
        return DegPerSec(self.value * factor)


@dataclass(frozen=True, order=True)
class RadPerSec:
    """An angular velocity in radians per second (`openarm_control` joint space)."""

    value: float

    def __add__(self, other: RadPerSec) -> RadPerSec:
        """Add another radians-per-second velocity."""
        return RadPerSec(self.value + other.value)

    def __sub__(self, other: RadPerSec) -> RadPerSec:
        """Subtract another radians-per-second velocity."""
        return RadPerSec(self.value - other.value)

    def scaled(self, factor: float) -> RadPerSec:
        """Scale by a dimensionless factor, staying in radians per second."""
        return RadPerSec(self.value * factor)


@dataclass(frozen=True, order=True)
class Nm:
    """A torque in newton-metres — the physical torque axis (`03` FR-MOT-037).

    Distinct from `PacketTorque`: a clamp expressed in Nm must never receive a
    packet-scale value, and the type is what forbids it.
    """

    value: float

    def __add__(self, other: Nm) -> Nm:
        """Add another newton-metre torque."""
        return Nm(self.value + other.value)

    def __sub__(self, other: Nm) -> Nm:
        """Subtract another newton-metre torque."""
        return Nm(self.value - other.value)

    def scaled(self, factor: float) -> Nm:
        """Scale by a dimensionless factor, staying in newton-metres."""
        return Nm(self.value * factor)


@dataclass(frozen=True, order=True)
class PacketTorque:
    """A torque in raw motor-packet scale (the DM `T_MAX` axis, `03` FR-MOT-037).

    This is the wire representation, not a physical quantity: the same number
    means different torques on different motors. It exists as its own type so a
    physical-torque clamp cannot silently accept a packet-scale value; crossing to
    `Nm` requires the explicit `packet_to_nm` conversion with a per-motor scale.
    """

    value: int
