"""Acceptance ① ②: link7 collision coverage (URDF+MJCF), margin policy, virtual walls.

The MJCF check runs over the committed WP-0C-03 asset and genuinely passes — the wrist-distal
`ee_base_link` carries a collision geom on both arms. The URDF side runs over this WP's
injected sim/safety descriptor (the FR-SAF-010 injection remedy); the vendor URDF is not
committed, so its verification is the deferred-fixture concern, not this one.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from backend.safety_bringup import (
    Link7CollisionMissingError,
    MarginConfirmationRequiredError,
    assert_link7_collision_in_mjcf,
    assert_link7_collision_in_urdf,
    committed_mjcf_path,
    count_virtual_wall_geoms,
    inject_link7_collision_urdf,
    inject_virtual_walls,
    resolve_collision_margin,
)
from backend.safety_bringup.constants import COLLISION_MARGIN_DEFAULT_M


def test_committed_mjcf_resolves_through_owning_package() -> None:
    # The WP-0C-03 asset is located through sim.mjcf, not a hardcoded string, and exists.
    path = committed_mjcf_path()
    assert path.is_file()
    assert path.name == "openarm_bimanual.xml"
    assert path.parent.parent.name == "mjcf"


def test_link7_collision_present_in_committed_mjcf(committed_mjcf: Path) -> None:
    # ①: both arms' joint-7 bodies (ee_base_link) declare a collision geom.
    bodies = assert_link7_collision_in_mjcf(committed_mjcf)
    assert bodies == ("openarm_left_ee_base_link", "openarm_right_ee_base_link")


def test_link7_missing_collision_in_mjcf_is_refused(tmp_path: Path, committed_mjcf: Path) -> None:
    # ①: strip the collision geoms from a copy => the check refuses (injection required).
    root = ET.parse(committed_mjcf).getroot()
    for body in root.iter("body"):
        joints = [joint.get("name", "") for joint in body.findall("joint")]
        if any(name.endswith("joint7") for name in joints):
            for geom in list(body.findall("geom")):
                if geom.get("class") == "collision":
                    body.remove(geom)
    stripped = tmp_path / "no_link7_collision.xml"
    ET.ElementTree(root).write(stripped, encoding="unicode")
    with pytest.raises(Link7CollisionMissingError, match="collision"):
        assert_link7_collision_in_mjcf(stripped)


def test_injected_urdf_carries_link7_collision(injected_urdf: Path) -> None:
    # ①: the committed injected descriptor declares link7 with a <collision> element.
    assert assert_link7_collision_in_urdf(injected_urdf) == "link7"


def test_injected_urdf_bytes_match_the_injector(tmp_path: Path, injected_urdf: Path) -> None:
    # The committed asset is exactly what the injector writes — no hand editing.
    fresh = inject_link7_collision_urdf(tmp_path / "openarm_link7_collision.urdf")
    assert fresh.read_text(encoding="utf-8") == injected_urdf.read_text(encoding="utf-8")


def test_urdf_without_collision_is_refused(tmp_path: Path) -> None:
    # ①: a link7 with only visual geometry is invisible to the collision engine.
    urdf = tmp_path / "visual_only.urdf"
    urdf.write_text('<robot name="x"><link name="link7"><visual/></link></robot>', encoding="utf-8")
    with pytest.raises(Link7CollisionMissingError, match="collision"):
        assert_link7_collision_in_urdf(urdf)


def test_margin_default_is_at_least_two_centimetres() -> None:
    # ②: the default margin is >= 0.02 m.
    resolution = resolve_collision_margin(requested_m=None, confirmed=False)
    assert resolution.margin_m >= COLLISION_MARGIN_DEFAULT_M
    assert resolution.margin_m == 0.02


def test_zero_margin_requires_explicit_confirmation() -> None:
    # ②: a zero margin without confirmation is refused (warn + confirm).
    with pytest.raises(MarginConfirmationRequiredError):
        resolve_collision_margin(requested_m=0.0, confirmed=False)


def test_zero_margin_with_confirmation_warns_and_is_honoured() -> None:
    # ②: confirmed zero is honoured but carries a warning.
    resolution = resolve_collision_margin(requested_m=0.0, confirmed=True)
    assert resolution.margin_m == 0.0
    assert "0 m" in resolution.warning


def test_below_default_margin_warns() -> None:
    resolution = resolve_collision_margin(requested_m=0.01, confirmed=False)
    assert resolution.margin_m == 0.01
    assert "below" in resolution.warning


def test_virtual_walls_are_injected_as_collision_geoms(injected_walls: Path) -> None:
    # FR-SAF-013: the injected scene declares workspace virtual walls as collision geoms.
    assert count_virtual_wall_geoms(injected_walls) == 6


def test_virtual_walls_bytes_match_the_injector(tmp_path: Path, injected_walls: Path) -> None:
    fresh = inject_virtual_walls(tmp_path / "virtual_walls.xml")
    assert fresh.read_text(encoding="utf-8") == injected_walls.read_text(encoding="utf-8")
