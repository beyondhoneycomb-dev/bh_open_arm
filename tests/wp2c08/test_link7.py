"""Acceptance ④: link7 collision geom exists in URDF and MJCF; absence triggers the variant."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.collision_preflight.link7 import (
    inject_approx_cylinder_variant,
    materialize_link7_urdf,
    verify_link7_both,
)
from backend.safety_bringup.collision import (
    Link7CollisionMissingError,
    assert_link7_collision_in_mjcf,
)

# A minimal MJCF whose joint-7 body carries only a visual geom — the RETRY_WITH_VARIANT
# trigger. It is parsed as XML (the reused check reads what the asset declares), so it need
# not be a compilable model.
_STRIPPED_MJCF = """<?xml version="1.0"?>
<mujoco model="stripped">
  <worldbody>
    <body name="openarm_left_ee_base_link">
      <joint name="openarm_left_joint7"/>
      <geom name="ee_visual" class="visual"/>
    </body>
  </worldbody>
</mujoco>
"""


def test_link7_present_in_both_assets(tmp_path: Path) -> None:
    urdf = materialize_link7_urdf(tmp_path / "link7.urdf")
    verification = verify_link7_both(urdf)
    # Both arms pass in the committed MJCF; the URDF descriptor's link7 passes.
    assert len(verification.mjcf_bodies) == 2
    assert verification.urdf_link == "link7"


def test_materialized_urdf_has_link7_collision(tmp_path: Path) -> None:
    urdf = materialize_link7_urdf(tmp_path / "link7.urdf")
    assert urdf.is_file()
    assert "collision" in urdf.read_text(encoding="utf-8")


def test_stripped_mjcf_is_detected(tmp_path: Path) -> None:
    stripped = tmp_path / "stripped.xml"
    stripped.write_text(_STRIPPED_MJCF, encoding="utf-8")
    with pytest.raises(Link7CollisionMissingError):
        assert_link7_collision_in_mjcf(stripped)


def test_approx_cylinder_variant_repairs_a_stripped_mjcf(tmp_path: Path) -> None:
    stripped = tmp_path / "stripped.xml"
    stripped.write_text(_STRIPPED_MJCF, encoding="utf-8")

    repaired = inject_approx_cylinder_variant(stripped, tmp_path / "repaired.xml")
    # The RETRY_WITH_VARIANT remedy makes the reused check pass, without touching the source.
    bodies = assert_link7_collision_in_mjcf(repaired)
    assert bodies == ("openarm_left_ee_base_link",)
    with pytest.raises(Link7CollisionMissingError):
        assert_link7_collision_in_mjcf(stripped)


def test_variant_refuses_a_source_without_joint7(tmp_path: Path) -> None:
    no_joint7 = tmp_path / "nojoint7.xml"
    no_joint7.write_text(
        '<?xml version="1.0"?><mujoco><worldbody>'
        '<body name="base"><geom name="g" class="collision"/></body>'
        "</worldbody></mujoco>",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="joint7"):
        inject_approx_cylinder_variant(no_joint7, tmp_path / "out.xml")
