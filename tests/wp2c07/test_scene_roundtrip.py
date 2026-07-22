"""Acceptance ② — a defined wall visualises, edits, saves, and reloads.

`02b` §1.2 WP-2C-07 ②: the offline scene round-trip. A wall is defined and edited,
saved, and reloaded to an equal scene; the fragment compiles in MuJoCo (the offline
sense of "visualises"), and WP-1-06's own `count_virtual_wall_geoms` counts the geoms
this WP writes — one scene dialect, not two. The interactive 3D viewport is the GUI
wave's (S-12, `02d`) and is out of scope here.
"""

from __future__ import annotations

from pathlib import Path

import mujoco
import pytest

from backend.safety_bringup.collision import count_virtual_wall_geoms
from sim.walls import (
    DuplicateWallError,
    WallGeom,
    WallNotFoundError,
    WallScene,
    WallShape,
    seed_from_injector,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EXAMPLE_SCENE = _REPO_ROOT / "sim" / "walls" / "scene" / "example_virtual_walls.xml"


def _sample_scene() -> WallScene:
    """A two-wall scene: a box keep-out and a ground plane."""
    return WallScene(
        (
            WallGeom("vw_box", WallShape.BOX, (1.0, 0.0, 0.5), (0.1, 0.2, 0.3)),
            WallGeom("vw_plane", WallShape.PLANE, (0.0, 0.0, 0.0), (2.0, 2.0, 0.05)),
        )
    )


def test_define_edit_save_reload_round_trips(tmp_path: Path) -> None:
    """A defined-then-edited scene reloads to an equal scene (②)."""
    scene = _sample_scene()
    scene.edit("vw_box", pos=(1.1, 0.0, 0.5), size=(0.15, 0.2, 0.3))
    dest = tmp_path / "walls.xml"
    scene.save(dest)
    assert WallScene.load(dest) == scene


def test_saved_scene_compiles_in_mujoco(tmp_path: Path) -> None:
    """The saved fragment is a loadable MuJoCo model — the offline 'visualises' (②)."""
    dest = _sample_scene().save(tmp_path / "walls.xml")
    model = mujoco.MjModel.from_xml_path(str(dest))
    assert model.ngeom == 2


def test_wp106_counter_counts_written_geoms(tmp_path: Path) -> None:
    """WP-1-06's collision-geom counter counts this WP's geoms — shared scene shape."""
    dest = _sample_scene().save(tmp_path / "walls.xml")
    assert count_virtual_wall_geoms(dest) == 2


def test_committed_example_scene_round_trips() -> None:
    """The committed example scene loads and re-serialises identically."""
    loaded = WallScene.load(_EXAMPLE_SCENE)
    assert len(loaded) == 2
    assert WallScene.load(_EXAMPLE_SCENE) == loaded


def test_seed_from_injector_reuses_wp106(tmp_path: Path) -> None:
    """The WP-1-06 injector's fixed walls become an editable, round-tripping scene."""
    seed_path = tmp_path / "seed.xml"
    seeded = seed_from_injector(seed_path)
    assert len(seeded) == count_virtual_wall_geoms(seed_path)
    seeded.remove("wall_ceiling")
    edited = seeded.save(tmp_path / "edited.xml")
    assert WallScene.load(edited) == seeded


def test_add_edit_remove_semantics(tmp_path: Path) -> None:
    """add/edit/remove behave: reject duplicate, reject missing, remove by name."""
    scene = _sample_scene()
    with pytest.raises(DuplicateWallError):
        scene.add(WallGeom("vw_box", WallShape.BOX, (0, 0, 0), (0.1, 0.1, 0.1)))
    with pytest.raises(WallNotFoundError):
        scene.edit("nope", pos=(0, 0, 0))
    with pytest.raises(WallNotFoundError):
        scene.remove("nope")
    scene.remove("vw_box")
    assert scene.names() == ("vw_plane",)


def test_load_ignores_non_collision_geoms(tmp_path: Path) -> None:
    """Only collision-class geoms are read back; visual geoms invent no walls."""
    xml = (
        '<mujoco model="mix">\n'
        "  <worldbody>\n"
        '    <geom name="w" class="collision" type="box" pos="0 0 0" size="0.1 0.1 0.1"/>\n'
        '    <geom name="v" type="box" pos="1 1 1" size="0.1 0.1 0.1"/>\n'
        "  </worldbody>\n"
        "</mujoco>\n"
    )
    path = tmp_path / "mixed.xml"
    path.write_text(xml, encoding="utf-8")
    scene = WallScene.load(path)
    assert scene.names() == ("w",)
