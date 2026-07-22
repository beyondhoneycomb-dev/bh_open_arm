"""WallGeom validation: an edited or defined wall can never be silently inert.

`12` FR-SAF-013: a virtual wall is a collision geom. A box with a non-positive
half-extent or a plane with non-positive spacing compiles to a geom that takes part in
no contact — an invisible keep-out, the exact silent-disable this WP guards against — so
construction and editing reject those rather than accept them.
"""

from __future__ import annotations

import pytest

from sim.walls import WallGeom, WallGeomError, WallShape


def test_box_requires_positive_half_extents() -> None:
    """A box with a zero half-extent has no volume and is rejected."""
    with pytest.raises(WallGeomError):
        WallGeom("b", WallShape.BOX, (0, 0, 0), (0.1, 0.0, 0.1))


def test_plane_requires_positive_spacing() -> None:
    """A plane's grid spacing (third size component) must be positive."""
    with pytest.raises(WallGeomError):
        WallGeom("p", WallShape.PLANE, (0, 0, 0), (1.0, 1.0, 0.0))


def test_plane_allows_infinite_half_extents() -> None:
    """A plane half-extent of zero means infinite and is allowed."""
    geom = WallGeom("p", WallShape.PLANE, (0, 0, 0), (0.0, 0.0, 0.05))
    assert geom.size == (0.0, 0.0, 0.05)


def test_plane_rejects_negative_half_extent() -> None:
    """A negative plane half-extent is not a size and is rejected."""
    with pytest.raises(WallGeomError):
        WallGeom("p", WallShape.PLANE, (0, 0, 0), (-1.0, 1.0, 0.05))


def test_name_must_be_an_identifier() -> None:
    """A name that is not a MuJoCo identifier is rejected before it reaches XML."""
    with pytest.raises(WallGeomError):
        WallGeom("bad name", WallShape.BOX, (0, 0, 0), (0.1, 0.1, 0.1))
    with pytest.raises(WallGeomError):
        WallGeom('x"/>', WallShape.BOX, (0, 0, 0), (0.1, 0.1, 0.1))


def test_vectors_must_be_length_three() -> None:
    """Position and size are 3-vectors; other arities are rejected."""
    with pytest.raises(WallGeomError):
        WallGeom("b", WallShape.BOX, (0, 0), (0.1, 0.1, 0.1))  # type: ignore[arg-type]


def test_edited_keeps_name_and_revalidates() -> None:
    """An edit keeps the wall's identity and re-runs the dimension rule."""
    geom = WallGeom("b", WallShape.BOX, (0, 0, 0), (0.1, 0.1, 0.1))
    moved = geom.edited(pos=(1.0, 2.0, 3.0))
    assert moved.name == "b"
    assert moved.pos == (1.0, 2.0, 3.0)
    with pytest.raises(WallGeomError):
        geom.edited(size=(0.0, 0.1, 0.1))


def test_frozen_value_is_not_mutated_by_edit() -> None:
    """Editing yields a new value; the original is unchanged."""
    geom = WallGeom("b", WallShape.BOX, (0, 0, 0), (0.1, 0.1, 0.1))
    geom.edited(pos=(9.0, 9.0, 9.0))
    assert geom.pos == (0.0, 0.0, 0.0)
