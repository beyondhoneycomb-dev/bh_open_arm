"""Editable box/plane virtual-wall geoms — the value type the 3D editor manipulates.

`12` FR-SAF-013 environment virtual walls are box/plane collision geoms. WP-1-06
(`backend.safety_bringup.collision`) injects a *fixed* workspace box as one MJCF
scene fragment; this WP adds the piece that fragment cannot express — a geom the
operator can define, edit (move/resize/reshape), and round-trip through a scene
file. `WallGeom` is that editable value: one immutable box or plane, validated on
construction, with `edited()` returning the changed copy an edit produces.

The geom is serialised in WP-1-06's own scene shape — a `class="collision"` geom in
a MuJoCo worldbody — so a fragment this module writes is counted by
`count_virtual_wall_geoms` and loaded by anything that reads WP-1-06's output, and
the two wall paths never diverge into a second scene dialect.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from enum import Enum

# A plane's third size component is MuJoCo's grid-rendering spacing, not a half-extent;
# it must be positive for the geom to render, while the first two (half-extents) may be
# zero to mean "infinite". A box's three components are all half-extents and must be
# positive, or the box has no volume and takes part in no contact.
_PLANE_SPACING_INDEX = 2
_VEC3_LEN = 3

# Geom names become MJCF attribute values and MuJoCo identifiers; restrict them to the
# identifier alphabet so a name can never inject XML or collide with attribute syntax.
_GEOM_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


class WallShape(Enum):
    """The collision-geom primitive a virtual wall is built from (`12` FR-SAF-013).

    The value is the MuJoCo geom ``type`` string, so serialisation is the enum value
    verbatim and no separate shape-to-string table can drift from it.
    """

    BOX = "box"
    PLANE = "plane"


class WallGeomError(ValueError):
    """Raised when a wall geom's shape, name, or dimensions are invalid.

    A geom that fails these checks would either not serialise to a legal MJCF geom or
    would compile to one that takes part in no contact — a silently inert wall, which
    for a safety keep-out is the failure this WP exists to prevent.
    """


@dataclass(frozen=True)
class WallGeom:
    """One editable virtual-wall collision geom: a box or a plane (`12` FR-SAF-013).

    Immutable by construction so an edit is an explicit new value (`edited()`), never a
    hidden in-place mutation that a holder of the old reference would miss. Positions
    are metres in the scene frame; sizes are MuJoCo half-extents (box) or
    half-extents-plus-spacing (plane).

    Attributes:
        name: MuJoCo geom identifier; identifier alphabet only.
        shape: Box or plane primitive.
        pos: Centre position (x, y, z) in metres.
        size: Box half-extents (x, y, z), or plane (half-x, half-y, grid spacing).
    """

    name: str
    shape: WallShape
    pos: tuple[float, float, float]
    size: tuple[float, float, float]

    def __post_init__(self) -> None:
        """Validate the name, the vector arity, and the shape's dimension rule.

        Raises:
            WallGeomError: If the name is not an identifier, a vector is not length 3,
                or a dimension violates the shape's positivity rule.
        """
        if not _GEOM_NAME.match(self.name):
            raise WallGeomError(
                f"wall geom name {self.name!r} is not an identifier "
                "([A-Za-z][A-Za-z0-9_]*); it must be a legal MuJoCo geom name"
            )
        object.__setattr__(self, "pos", _as_vec3(self.pos, "pos"))
        object.__setattr__(self, "size", _as_vec3(self.size, "size"))
        if self.shape is WallShape.BOX:
            if any(component <= 0.0 for component in self.size):
                raise WallGeomError(
                    f"box wall {self.name!r} has a non-positive half-extent {self.size}; "
                    "a zero-volume box takes part in no contact (12 FR-SAF-013)"
                )
        else:
            spacing = self.size[_PLANE_SPACING_INDEX]
            if spacing <= 0.0:
                raise WallGeomError(
                    f"plane wall {self.name!r} has grid spacing {spacing} <= 0; "
                    "MuJoCo requires a positive plane spacing"
                )
            if any(component < 0.0 for component in self.size[:_PLANE_SPACING_INDEX]):
                raise WallGeomError(
                    f"plane wall {self.name!r} has a negative half-extent {self.size}; "
                    "a plane half-extent is >= 0 (0 meaning infinite)"
                )

    def edited(
        self,
        shape: WallShape | None = None,
        pos: tuple[float, float, float] | None = None,
        size: tuple[float, float, float] | None = None,
    ) -> WallGeom:
        """Return a copy with the given fields changed — the editor's edit operation.

        The name is fixed: a wall keeps its identity across edits so a scene can find
        and replace it. Changing shape/pos/size re-runs validation, so an edit can
        never produce an inert geom.

        Args:
            shape: New primitive, or None to keep.
            pos: New centre position, or None to keep.
            size: New dimensions, or None to keep.

        Returns:
            (WallGeom) The edited geom.

        Raises:
            WallGeomError: If the edited dimensions violate the shape's rule.
        """
        return replace(
            self,
            shape=self.shape if shape is None else shape,
            pos=self.pos if pos is None else pos,
            size=self.size if size is None else size,
        )


def _as_vec3(value: tuple[float, float, float], field_name: str) -> tuple[float, float, float]:
    """Coerce a 3-vector to a float tuple, rejecting the wrong arity.

    Args:
        value: The candidate vector.
        field_name: Name used in the error message.

    Returns:
        (tuple[float, float, float]) The vector as floats.

    Raises:
        WallGeomError: If the vector is not length 3.
    """
    components = tuple(value)
    if len(components) != _VEC3_LEN:
        raise WallGeomError(f"{field_name} must be a 3-vector, got {components!r}")
    return (float(components[0]), float(components[1]), float(components[2]))
