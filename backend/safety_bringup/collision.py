"""link7 collision coverage, the collision margin policy, and virtual-wall injection.

Three `12` requirements:

  * FR-SAF-010 — link7 (the wrist-distal link, `ee_base_link` in the vendored MJCF) must be
    in collision checking, verified in the URDF and the MJCF each. The committed MJCF is
    READ, never written (`WP-0C-03` owns it exclusively); a missing collision geom is
    remedied by injecting into a scene variant under this WP's own `sim/safety` tree, not
    by editing the vendor asset.
  * FR-SAF-011 — the collision margin default is >= 0.02 m; a request of exactly zero warns
    and additionally requires an explicit confirmation before it is honoured.
  * FR-SAF-013 — environment virtual walls are box/plane collision geoms injected into an
    MJCF scene; again into `sim/safety`, not the vendor MJCF.

The MJCF is parsed as XML directly rather than through the MuJoCo compiler, matching the
`WP-0C-03` invariant checker: the question is what the asset *declares* for link7, which a
compiled model would paper over.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import sim.mjcf
from backend.safety_bringup.constants import (
    COLLISION_MARGIN_DEFAULT_M,
    MJCF_COLLISION_CLASS,
    MJCF_JOINT7_SUFFIX,
)

# The URDF link and collision element the injected descriptor declares for the wrist-distal
# link. The descriptor is this WP's `sim/safety` collision variant (the FR-SAF-010 injection
# remedy), not a copy of the vendor kinematic tree.
URDF_WRIST_DISTAL_LINK = "link7"

# The committed bimanual MJCF, relative to the sim.mjcf package root (WP-0C-03 asset).
_COMMITTED_MJCF_RELPATH = ("v2", "openarm_bimanual.xml")


def committed_mjcf_path() -> Path:
    """Locate the committed WP-0C-03 bimanual MJCF through its owning package (READ only).

    Resolving through `sim.mjcf` rather than a hardcoded repo-relative string keeps the
    dependency on the vendored asset explicit and pinned to the owning package: this WP
    READs that MJCF for the link7 check and never writes it (`WP-0C-03` owns it exclusively).

    Returns:
        (Path) The path to `sim/mjcf/v2/openarm_bimanual.xml`.

    Raises:
        RuntimeError: If the `sim.mjcf` package has no file location to resolve against.
    """
    package_file = sim.mjcf.__file__
    if package_file is None:
        raise RuntimeError("sim.mjcf has no __file__; cannot locate the committed MJCF")
    return Path(package_file).resolve().parent.joinpath(*_COMMITTED_MJCF_RELPATH)


class Link7CollisionMissingError(Exception):
    """Raised when the wrist-distal link carries no collision geom in a checked asset.

    `12` FR-SAF-010 requires link7 to be in collision checking; a body or link declaring
    only visual geometry is invisible to the collision engine, so it is refused until the
    collision geom is injected.
    """


def _body_joint_suffixes(body: ET.Element) -> list[str]:
    """Return the names of joints declared directly under a MJCF body.

    Args:
        body: A MJCF `<body>` element.

    Returns:
        (list[str]) The `name` of each direct-child `<joint>`.
    """
    return [joint.get("name", "") for joint in body.findall("joint")]


def _body_has_collision_geom(body: ET.Element) -> bool:
    """Report whether a MJCF body declares a collision-class geom directly.

    Args:
        body: A MJCF `<body>` element.

    Returns:
        (bool) True when a direct-child `<geom>` has `class="collision"`.
    """
    return any(geom.get("class") == MJCF_COLLISION_CLASS for geom in body.findall("geom"))


def _joint7_bodies(element: ET.Element) -> list[ET.Element]:
    """Find every body that owns a `*joint7`, recursively (both arms).

    Args:
        element: The XML element to search under.

    Returns:
        (list[ET.Element]) The bodies whose direct-child joint names end with `joint7`.
    """
    found: list[ET.Element] = []
    for body in element.iter("body"):
        if any(name.endswith(MJCF_JOINT7_SUFFIX) for name in _body_joint_suffixes(body)):
            found.append(body)
    return found


def assert_link7_collision_in_mjcf(mjcf_path: Path) -> tuple[str, ...]:
    """Verify link7 carries a collision geom in a committed MJCF, per arm (`12` FR-SAF-010).

    Args:
        mjcf_path: Path to the MJCF to READ (the vendored `WP-0C-03` asset).

    Returns:
        (tuple[str, ...]) The names of the joint-7 bodies that passed, one per arm.

    Raises:
        Link7CollisionMissingError: If no joint-7 body is present, or any joint-7 body
            declares no collision geom.
    """
    root = ET.parse(mjcf_path).getroot()
    bodies = _joint7_bodies(root)
    if not bodies:
        raise Link7CollisionMissingError(
            f"{mjcf_path} declares no body owning a *{MJCF_JOINT7_SUFFIX}; link7 cannot be "
            "in collision checking (12 FR-SAF-010)"
        )
    passed: list[str] = []
    for body in bodies:
        name = body.get("name", "<unnamed>")
        if not _body_has_collision_geom(body):
            raise Link7CollisionMissingError(
                f"{mjcf_path}: link7 body {name!r} declares no collision-class geom; it is "
                "invisible to the collision engine (12 FR-SAF-010)"
            )
        passed.append(name)
    return tuple(passed)


def assert_link7_collision_in_urdf(urdf_path: Path) -> str:
    """Verify link7 carries a `<collision>` element in a URDF (`12` FR-SAF-010).

    Args:
        urdf_path: Path to the URDF collision descriptor to READ.

    Returns:
        (str) The name of the link that passed.

    Raises:
        Link7CollisionMissingError: If the wrist-distal link is absent or declares no
            `<collision>` child.
    """
    root = ET.parse(urdf_path).getroot()
    for link in root.findall("link"):
        name = link.get("name", "")
        if name.endswith(URDF_WRIST_DISTAL_LINK):
            if link.find("collision") is None:
                raise Link7CollisionMissingError(
                    f"{urdf_path}: link {name!r} declares no <collision> element (12 FR-SAF-010)"
                )
            return name
    raise Link7CollisionMissingError(
        f"{urdf_path} declares no *{URDF_WRIST_DISTAL_LINK} link (12 FR-SAF-010)"
    )


def inject_link7_collision_urdf(dest: Path) -> Path:
    """Write the wrist-distal collision descriptor into this WP's `sim/safety` tree.

    This is the FR-SAF-010 injection remedy for the URDF side: the repo commits no vendor
    URDF, so the collision requirement for link7 is carried by this minimal descriptor —
    the wrist-distal link with a box collision element sized to the MJCF `ee_base_link`
    envelope. It is deliberately not a copy of the vendor kinematic tree; it is the
    collision-coverage assertion for one link, written where this WP is allowed to own it.

    Args:
        dest: Destination path under `sim/safety`.

    Returns:
        (Path) The written descriptor path.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(_LINK7_COLLISION_URDF, encoding="utf-8")
    return dest


@dataclass(frozen=True)
class MarginResolution:
    """The outcome of resolving a requested collision margin (`12` FR-SAF-011).

    Attributes:
        margin_m: The margin that was honoured, metres.
        warning: A warning when the request is below the default, else empty.
    """

    margin_m: float
    warning: str


class MarginConfirmationRequiredError(Exception):
    """Raised when a zero collision margin is requested without explicit confirmation.

    `12` FR-SAF-011 requires a zero margin — collision checking with no buffer — to be
    warned and explicitly confirmed, not accepted silently.
    """


def resolve_collision_margin(requested_m: float | None, confirmed: bool) -> MarginResolution:
    """Resolve a collision margin against the default, warning and gating zero (② / FR-SAF-011).

    Args:
        requested_m: The requested margin in metres, or None to take the default.
        confirmed: Whether the operator explicitly confirmed a zero margin.

    Returns:
        (MarginResolution) The honoured margin and any warning.

    Raises:
        MarginConfirmationRequiredError: If a zero margin is requested without confirmation.
    """
    if requested_m is None:
        return MarginResolution(margin_m=COLLISION_MARGIN_DEFAULT_M, warning="")
    if requested_m == 0.0:
        if not confirmed:
            raise MarginConfirmationRequiredError(
                "collision margin 0 m disables the buffer; it must be explicitly confirmed "
                "(12 FR-SAF-011, acceptance ②)"
            )
        return MarginResolution(
            margin_m=0.0, warning="collision margin set to 0 m: no buffer, explicitly confirmed"
        )
    if requested_m < COLLISION_MARGIN_DEFAULT_M:
        return MarginResolution(
            margin_m=requested_m,
            warning=(
                f"collision margin {requested_m} m is below the {COLLISION_MARGIN_DEFAULT_M} m "
                "default (12 FR-SAF-011)"
            ),
        )
    return MarginResolution(margin_m=requested_m, warning="")


def inject_virtual_walls(dest: Path) -> Path:
    """Write the workspace virtual-wall MJCF scene fragment into `sim/safety` (`12` FR-SAF-013).

    The walls are box/plane collision geoms bounding the workspace, injected into this WP's
    own scene variant rather than the vendor MJCF. Environment collision is MJCF cell geom,
    not an octomap depth pipeline (FR-SAF-012), so these geoms are the environment-collision
    input for the cell.

    Args:
        dest: Destination path under `sim/safety`.

    Returns:
        (Path) The written scene-fragment path.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(_VIRTUAL_WALLS_MJCF, encoding="utf-8")
    return dest


def count_virtual_wall_geoms(scene_path: Path) -> int:
    """Count the collision-class geoms in a virtual-wall scene fragment (`12` FR-SAF-013).

    Args:
        scene_path: Path to the scene fragment to READ.

    Returns:
        (int) The number of `class="collision"` geoms declared.
    """
    root = ET.parse(scene_path).getroot()
    return sum(1 for geom in root.iter("geom") if geom.get("class") == MJCF_COLLISION_CLASS)


# A box collision element on the wrist-distal link. Half-extents approximate the MJCF
# `ee_base_link` envelope; the point of the descriptor is collision coverage of link7, not
# a metrically exact hull (12 FR-SAF-010).
_LINK7_COLLISION_URDF = """<?xml version="1.0"?>
<!-- WP-1-06 sim/safety collision descriptor: link7 (wrist-distal) collision coverage.
     Injection remedy for 12 FR-SAF-010 on the URDF side; the repo vendors no full URDF,
     and the vendor URDF is re-verified by the fixture hook. NOT a copy of the kinematic
     tree. -->
<robot name="openarm_link7_collision">
  <link name="link7">
    <collision>
      <origin xyz="0.0205 0 -0.03" rpy="0 0 0"/>
      <geometry>
        <box size="0.06 0.05 0.10"/>
      </geometry>
    </collision>
  </link>
</robot>
"""

# Six axis-aligned virtual walls (a workspace box) plus a floor plane, as collision-class
# geoms in a MuJoCo worldbody fragment. Injected into sim/safety, included alongside the
# cell scene; this is the environment-collision input FR-SAF-012 leaves to MJCF cell geom.
_VIRTUAL_WALLS_MJCF = """<?xml version="1.0"?>
<!-- WP-1-06 sim/safety scene variant: workspace virtual walls as MJCF collision geoms.
     12 FR-SAF-013 injection; owned under sim/safety, NOT the WP-0C-03 vendor MJCF. -->
<mujoco model="openarm_virtual_walls">
  <default>
    <default class="collision">
      <geom group="3" contype="1" conaffinity="1"/>
    </default>
  </default>
  <worldbody>
    <geom name="wall_floor" class="collision" type="plane" pos="0 0 0" size="1.5 1.5 0.01"/>
    <geom name="wall_ceiling" class="collision" type="box" pos="0 0 1.6" size="1.0 1.0 0.02"/>
    <geom name="wall_front" class="collision" type="box" pos="0.9 0 0.8" size="0.02 1.0 0.8"/>
    <geom name="wall_back" class="collision" type="box" pos="-0.9 0 0.8" size="0.02 1.0 0.8"/>
    <geom name="wall_left" class="collision" type="box" pos="0 0.9 0.8" size="1.0 0.02 0.8"/>
    <geom name="wall_right" class="collision" type="box" pos="0 -0.9 0.8" size="1.0 0.02 0.8"/>
  </worldbody>
</mujoco>
"""
