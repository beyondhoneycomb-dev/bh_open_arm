"""An editable set of virtual-wall geoms with a lossless scene-file round-trip.

`12` FR-SAF-013 / FR-SIM-034: a defined virtual wall must visualise, edit, save, and
reload. `WallScene` is the edit surface (add / edit / remove) and the persistence
surface (`save` / `load`) behind that requirement — the offline half of "3D edit and
save", the interactive viewport being the GUI wave's (S-12, `02d`) and deferred here.

The serialised form is WP-1-06's scene shape, not a new one: each wall is a
``class="collision"`` geom in a MuJoCo worldbody, so a scene this writes is counted by
`count_virtual_wall_geoms` (reused) and read by anything that reads WP-1-06's injector
output. `seed_from_injector` closes that loop the other way — it takes the WP-1-06
injector's fixed workspace box as the starting scene an operator then edits, rather
than re-declaring those walls here (no second injector).

Round-trip contract: for any scene ``s``, ``WallScene.load(s.save(p)) == s``. Floats
are written with `repr`, whose shortest round-tripping form is exact, so save/reload
preserves every coordinate.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from backend.safety_bringup.constants import MJCF_COLLISION_CLASS
from sim.walls.geoms import WallGeom, WallGeomError, WallShape

# The scene wraps its geoms in the same collision-class default block WP-1-06 writes, so
# a compiler applies contype/conaffinity=1 to every wall and the fragment is contact-live
# the moment it loads. The model name marks the fragment as this WP's editable variant.
_SCENE_MODEL_NAME = "openarm_wp2c07_walls"


class DuplicateWallError(ValueError):
    """Raised when a wall name already present in the scene is added again.

    Names are geom identities: the editor finds and replaces a wall by name, so two
    walls sharing a name would make edit and remove ambiguous.
    """


class WallNotFoundError(KeyError):
    """Raised when an edit or removal names a wall the scene does not hold."""


class WallScene:
    """An ordered, name-keyed collection of editable virtual-wall geoms.

    Ownership/lifecycle: a mutable editor document. `add`/`edit`/`remove` mutate it in
    place; `save` serialises the current state; `load` constructs a fresh scene from a
    file. Two scenes are equal when they hold the same walls in the same order, which
    is what the save/reload round-trip is checked against.
    """

    def __init__(self, walls: tuple[WallGeom, ...] = ()) -> None:
        """Start a scene, optionally pre-populated.

        Args:
            walls: Initial walls, in order; names must be unique.

        Raises:
            DuplicateWallError: If two initial walls share a name.
        """
        self._walls: list[WallGeom] = []
        for wall in walls:
            self.add(wall)

    @property
    def walls(self) -> tuple[WallGeom, ...]:
        """The walls, in insertion order."""
        return tuple(self._walls)

    def names(self) -> tuple[str, ...]:
        """The wall names, in insertion order."""
        return tuple(wall.name for wall in self._walls)

    def __len__(self) -> int:
        """The number of walls in the scene."""
        return len(self._walls)

    def __eq__(self, other: object) -> bool:
        """Two scenes are equal when they hold identical walls in identical order."""
        if not isinstance(other, WallScene):
            return NotImplemented
        return self._walls == other._walls

    def __hash__(self) -> int:
        """Unhashable: a WallScene is a mutable document, not a value key."""
        raise TypeError("WallScene is mutable and not hashable")

    def _index_of(self, name: str) -> int:
        """Return the list index of the named wall.

        Args:
            name: Wall name to find.

        Returns:
            (int) Index in the ordered list.

        Raises:
            WallNotFoundError: If no wall carries the name.
        """
        for index, wall in enumerate(self._walls):
            if wall.name == name:
                return index
        raise WallNotFoundError(name)

    def get(self, name: str) -> WallGeom:
        """Return the named wall.

        Args:
            name: Wall name.

        Returns:
            (WallGeom) The wall.

        Raises:
            WallNotFoundError: If no wall carries the name.
        """
        return self._walls[self._index_of(name)]

    def add(self, wall: WallGeom) -> None:
        """Append a wall.

        Args:
            wall: The wall to add.

        Raises:
            DuplicateWallError: If a wall with the same name is already present.
        """
        if any(existing.name == wall.name for existing in self._walls):
            raise DuplicateWallError(f"wall {wall.name!r} is already in the scene")
        self._walls.append(wall)

    def edit(
        self,
        name: str,
        shape: WallShape | None = None,
        pos: tuple[float, float, float] | None = None,
        size: tuple[float, float, float] | None = None,
    ) -> WallGeom:
        """Replace the named wall with an edited copy, keeping its position in order.

        Args:
            name: Wall to edit.
            shape: New primitive, or None to keep.
            pos: New centre position, or None to keep.
            size: New dimensions, or None to keep.

        Returns:
            (WallGeom) The edited wall now in the scene.

        Raises:
            WallNotFoundError: If no wall carries the name.
            WallGeomError: If the edit yields an inert geom.
        """
        index = self._index_of(name)
        edited = self._walls[index].edited(shape=shape, pos=pos, size=size)
        self._walls[index] = edited
        return edited

    def remove(self, name: str) -> None:
        """Remove the named wall.

        Args:
            name: Wall to remove.

        Raises:
            WallNotFoundError: If no wall carries the name.
        """
        del self._walls[self._index_of(name)]

    def to_mjcf(self) -> str:
        """Serialise the scene to a MuJoCo XML fragment in WP-1-06's collision-class form.

        Returns:
            (str) A ``<mujoco>`` document whose worldbody holds one collision-class geom
            per wall, ready to compile or `count_virtual_wall_geoms`.
        """
        lines = [
            '<?xml version="1.0"?>',
            f'<mujoco model="{_SCENE_MODEL_NAME}">',
            "  <default>",
            f'    <default class="{MJCF_COLLISION_CLASS}">',
            '      <geom group="3" contype="1" conaffinity="1"/>',
            "    </default>",
            "  </default>",
            "  <worldbody>",
        ]
        for wall in self._walls:
            lines.append(
                f'    <geom name="{wall.name}" class="{MJCF_COLLISION_CLASS}" '
                f'type="{wall.shape.value}" pos="{_fmt_vec3(wall.pos)}" '
                f'size="{_fmt_vec3(wall.size)}"/>'
            )
        lines.append("  </worldbody>")
        lines.append("</mujoco>")
        return "\n".join(lines) + "\n"

    def save(self, dest: Path) -> Path:
        """Write the scene fragment to a file.

        Args:
            dest: Destination path; parent directories are created.

        Returns:
            (Path) The written path.
        """
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(self.to_mjcf(), encoding="utf-8")
        return dest

    @classmethod
    def load(cls, source: Path) -> WallScene:
        """Parse a collision-class wall fragment back into an editable scene.

        Only ``class="collision"`` geoms are read: a scene may hold visual or structural
        geoms this editor does not own, and reading those would let a reload invent walls
        the operator never defined.

        Args:
            source: Path to a scene fragment written by `save` or the WP-1-06 injector.

        Returns:
            (WallScene) The reconstructed scene.

        Raises:
            WallGeomError: If a collision geom names an unknown shape or bad dimensions.
        """
        root = ET.parse(source).getroot()
        walls: list[WallGeom] = []
        for geom in root.iter("geom"):
            if geom.get("class") != MJCF_COLLISION_CLASS:
                continue
            walls.append(
                WallGeom(
                    name=geom.get("name", ""),
                    shape=_shape_of(geom.get("type", "")),
                    pos=_parse_vec3(geom.get("pos", "")),
                    size=_parse_vec3(geom.get("size", "")),
                )
            )
        return cls(tuple(walls))


def seed_from_injector(dest: Path) -> WallScene:
    """Seed an editable scene from the WP-1-06 virtual-wall injector's output.

    Reuses `backend.safety_bringup.collision.inject_virtual_walls` — the fixed workspace
    box is written, then loaded as the starting document an operator edits. This is the
    reuse boundary: the injector remains the one source of the default walls, and this WP
    turns its output into something editable rather than declaring a second wall set.

    Args:
        dest: Path the injector writes and this scene loads from (under `sim/walls`).

    Returns:
        (WallScene) The injector's walls as an editable scene.
    """
    # Imported here, not at module load, so the editable-geom types carry no hard
    # import dependency on the injector; the seed path is the only place it is needed.
    from backend.safety_bringup.collision import inject_virtual_walls

    inject_virtual_walls(dest)
    return WallScene.load(dest)


def _shape_of(type_attr: str) -> WallShape:
    """Map a MuJoCo geom ``type`` string to a WallShape.

    Args:
        type_attr: The geom's ``type`` attribute.

    Returns:
        (WallShape) The matching primitive.

    Raises:
        WallGeomError: If the type is not a wall primitive (box or plane).
    """
    for shape in WallShape:
        if shape.value == type_attr:
            return shape
    raise WallGeomError(
        f"geom type {type_attr!r} is not a virtual-wall primitive "
        f"({[shape.value for shape in WallShape]})"
    )


def _parse_vec3(text: str) -> tuple[float, float, float]:
    """Parse a whitespace-separated 3-vector attribute.

    Args:
        text: The attribute text, e.g. ``"0.43 0.52 1.42"``.

    Returns:
        (tuple[float, float, float]) The parsed vector.

    Raises:
        WallGeomError: If the attribute does not hold exactly three numbers.
    """
    parts = text.split()
    if len(parts) != 3:
        raise WallGeomError(f"expected a 3-vector, got {text!r}")
    try:
        return (float(parts[0]), float(parts[1]), float(parts[2]))
    except ValueError as error:
        raise WallGeomError(f"non-numeric component in {text!r}") from error


def _fmt_vec3(vec: tuple[float, float, float]) -> str:
    """Format a 3-vector for MJCF using round-tripping float reprs.

    Args:
        vec: The vector to format.

    Returns:
        (str) Space-separated components whose `float()` recovers the input exactly.
    """
    return " ".join(repr(component) for component in vec)
