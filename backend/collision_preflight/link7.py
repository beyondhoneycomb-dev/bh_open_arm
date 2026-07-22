"""link7 collision-geom presence in the URDF and the MJCF, and the variant remedy (④).

`02b` WP-2C-08 ④ requires the wrist-distal link (link7) to carry a collision geom in the
URDF AND the MJCF: the URDF `collisions.yaml` has no link7, and a link absent from either
asset is invisible to that engine. This module does not re-implement the check — it reuses
`WP-1-06`'s (`backend.safety_bringup.collision`), which is the single home of the link7
coverage rule and the margin policy, and drives both sides through it.

The negative branch is `RETRY_WITH_VARIANT`: if the MJCF joint-7 body carries no collision
geom, the remedy is an approximate-cylinder collision geom injected into a scene VARIANT —
never the `WP-0C-03` vendor asset, which this WP only reads. The committed MJCF already
carries the `ee_base_link` collision geom, so on the real asset the variant is never taken;
the remedy exists so a stripped asset is repaired rather than silently passed.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.safety_bringup.collision import (
    assert_link7_collision_in_mjcf,
    assert_link7_collision_in_urdf,
    committed_mjcf_path,
    inject_link7_collision_urdf,
)
from backend.safety_bringup.constants import MJCF_COLLISION_CLASS, MJCF_JOINT7_SUFFIX


@dataclass(frozen=True)
class Link7Verification:
    """Evidence that link7 carries a collision geom in both assets (`02b` WP-2C-08 ④).

    Attributes:
        mjcf_bodies: The joint-7 bodies that passed in the MJCF, one per arm.
        urdf_link: The link that passed in the URDF descriptor.
    """

    mjcf_bodies: tuple[str, ...]
    urdf_link: str

    def as_record(self) -> dict[str, Any]:
        """Render the verification for an artifact.

        Returns:
            (dict[str, Any]) The passing MJCF bodies and URDF link.
        """
        return {"mjcf_bodies": list(self.mjcf_bodies), "urdf_link": self.urdf_link}


def materialize_link7_urdf(dest: Path) -> Path:
    """Write the `WP-1-06` link7 URDF collision descriptor to a path, for verification (④).

    The repo vendors no full URDF, so the URDF-side link7 collision coverage is carried by
    `WP-1-06`'s injected descriptor; this reuses that injector rather than writing a second
    descriptor.

    Args:
        dest: Where to write the descriptor.

    Returns:
        (Path) The written descriptor path.
    """
    return inject_link7_collision_urdf(dest)


def verify_link7_both(urdf_path: Path, mjcf_path: Path | None = None) -> Link7Verification:
    """Verify link7 carries a collision geom in the MJCF and the URDF, reusing `WP-1-06` (④).

    Args:
        urdf_path: The URDF collision descriptor to check (materialize one with
            `materialize_link7_urdf`).
        mjcf_path: The MJCF to check; None uses the committed `WP-0C-03` bimanual asset.

    Returns:
        (Link7Verification) The passing bodies and link.

    Raises:
        Link7CollisionMissingError: If either asset omits the link7 collision geom (raised
            by the reused `WP-1-06` checks; the MJCF case is the `RETRY_WITH_VARIANT` trigger).
    """
    mjcf = mjcf_path if mjcf_path is not None else committed_mjcf_path()
    mjcf_bodies = assert_link7_collision_in_mjcf(mjcf)
    urdf_link = assert_link7_collision_in_urdf(urdf_path)
    return Link7Verification(mjcf_bodies=mjcf_bodies, urdf_link=urdf_link)


def inject_approx_cylinder_variant(source_mjcf: Path, dest: Path) -> Path:
    """Repair a MJCF whose joint-7 bodies lack a collision geom, into a scene VARIANT (④).

    The `RETRY_WITH_VARIANT` remedy: an approximate-cylinder collision geom is added under
    each joint-7 body of a COPY of the source, written to `dest`. The vendor asset is never
    written — `02b` WP-2C-08 reads it — so this operates on a supplied source (a stripped
    asset or a mock) and emits a repaired variant that then passes the reused MJCF check.

    Args:
        source_mjcf: The MJCF to repair (READ only).
        dest: Where to write the repaired variant.

    Returns:
        (Path) The written variant path.

    Raises:
        ValueError: If the source declares no joint-7 body to repair.
    """
    tree = ET.parse(source_mjcf)
    root = tree.getroot()
    repaired = 0
    for body in root.iter("body"):
        joint_names = [joint.get("name", "") for joint in body.findall("joint")]
        if not any(name.endswith(MJCF_JOINT7_SUFFIX) for name in joint_names):
            continue
        body.append(_approx_cylinder_geom(body.get("name", "link7")))
        repaired += 1
    if repaired == 0:
        raise ValueError(
            f"{source_mjcf} declares no body owning a *{MJCF_JOINT7_SUFFIX}; nothing to repair"
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    tree.write(dest, encoding="unicode")
    return dest


def _approx_cylinder_geom(body_name: str) -> ET.Element:
    """Build the approximate-cylinder link7 collision geom element (the variant remedy).

    A capsule approximating the `ee_base_link` envelope, in the collision class so the
    reused MJCF check sees it. Its extent is deliberately conservative (it over-covers
    rather than under-covers the wrist-distal link).

    Args:
        body_name: The joint-7 body the geom is added to, used only to name the geom.

    Returns:
        (ET.Element) A `<geom>` element in the collision class.
    """
    geom = ET.Element("geom")
    geom.set("name", f"{body_name}_link7_approx_collision")
    geom.set("class", MJCF_COLLISION_CLASS)
    geom.set("type", "capsule")
    geom.set("fromto", "0.0205 0 0 0.0205 0 -0.10")
    geom.set("size", "0.035")
    return geom
