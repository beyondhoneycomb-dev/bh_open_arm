"""The collision preflight: waypoint qpos -> mj_forward -> first violating waypoint (①).

`02b` WP-2C-08 is a pre-check that runs before a trajectory is sent, and it is independent
of IK: `mink.CollisionAvoidanceLimit` is unused in the IK path, so an IK solution carries
no collision guarantee, and the preflight is the guarantee. It walks the waypoints, drives
each through `mj_forward`, and reports the FIRST waypoint whose configuration puts two
collision geoms within the safety margin — with the offending geoms, their separation, the
contact position, and the contact frame.

The check is reference-relative. Two links that are already within the margin at the safe
reference configuration (a home pose) are designed adjacency, not a collision, so the pairs
within margin at the reference form an allowed set and only pairs that become close along
the trajectory are violations. This is the discrete-sample equivalent of an allowed-
collision matrix; the reference must therefore be a collision-free configuration, which its
docstring states as a precondition.

Three gates run before the walk, each delegating to its single-source rule: the margin
policy (`WP-1-06`, acceptance ⑤), the self-collision activation proof (acceptance ③), and
the waypoint-density rule (acceptance ②). A trajectory too sparse to check, or a model
whose collision engine is dead, is refused here rather than walked to a vacuous pass.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from backend.collision_preflight.density import (
    DensityAssessment,
    require_sufficient_density,
)
from backend.collision_preflight.model import PreflightModel
from backend.collision_preflight.selfcollision import (
    SelfCollisionActivation,
    assert_self_collision_active,
)
from backend.safety_bringup.collision import MarginResolution, resolve_collision_margin


@dataclass(frozen=True)
class ContactReport:
    """One collision-geom contact, as the preflight reports it (`02b` WP-2C-08 ①).

    Attributes:
        geom1: Name of the first collision geom.
        geom2: Name of the second collision geom.
        dist_m: Signed separation, metres; negative is penetration, positive is within the
            safety margin.
        pos: The contact point in world coordinates, `(x, y, z)`.
        frame: The contact frame rotation, row-major 3x3 as nine floats.
    """

    geom1: str
    geom2: str
    dist_m: float
    pos: tuple[float, float, float]
    frame: tuple[float, ...]

    def as_record(self) -> dict[str, Any]:
        """Render the contact for an artifact.

        Returns:
            (dict[str, Any]) Every field of the contact.
        """
        return {
            "geom1": self.geom1,
            "geom2": self.geom2,
            "dist_m": self.dist_m,
            "pos": list(self.pos),
            "frame": list(self.frame),
        }


@dataclass(frozen=True)
class WaypointViolation:
    """The first waypoint whose configuration violates the margin (`02b` WP-2C-08 ①).

    Attributes:
        waypoint_index: Zero-based index of the first violating waypoint.
        contact: The closest offending contact at that waypoint.
    """

    waypoint_index: int
    contact: ContactReport

    def as_record(self) -> dict[str, Any]:
        """Render the violation for an artifact.

        Returns:
            (dict[str, Any]) The index and the contact.
        """
        return {"waypoint_index": self.waypoint_index, "contact": self.contact.as_record()}


@dataclass(frozen=True)
class PreflightResult:
    """The verdict of a preflight over one trajectory.

    Attributes:
        ok: True when no waypoint violated the margin.
        margin: The honoured margin and any warning (`WP-1-06` policy).
        self_collision: The proof the arm-arm pair test is live.
        density: The waypoint-density assessment.
        waypoints_checked: How many waypoints were walked (up to and including the first
            violation).
        first_violation: The first violating waypoint, or None when `ok`.
    """

    ok: bool
    margin: MarginResolution
    self_collision: SelfCollisionActivation
    density: DensityAssessment
    waypoints_checked: int
    first_violation: WaypointViolation | None

    def as_record(self) -> dict[str, Any]:
        """Render the whole verdict for an evidence artifact.

        Returns:
            (dict[str, Any]) The verdict and every piece of supporting evidence.
        """
        return {
            "ok": self.ok,
            "margin_m": self.margin.margin_m,
            "margin_warning": self.margin.warning,
            "self_collision": self.self_collision.as_record(),
            "density": self.density.as_record(),
            "waypoints_checked": self.waypoints_checked,
            "first_violation": (
                None if self.first_violation is None else self.first_violation.as_record()
            ),
        }


def _pair_key(geom1: int, geom2: int) -> tuple[int, int]:
    """Return an order-independent key for a geom pair.

    Args:
        geom1: One geom id.
        geom2: The other geom id.

    Returns:
        (tuple[int, int]) The two ids, smaller first.
    """
    return (geom1, geom2) if geom1 <= geom2 else (geom2, geom1)


def _within_margin_pairs(model: PreflightModel, qpos: Sequence[float]) -> set[tuple[int, int]]:
    """Return the set of geom pairs strictly within the margin at a configuration.

    MuJoCo widens a dynamic pair's contact-generation threshold to the sum of the two geom
    margins, so `data.contact[]` carries pairs beyond the safety margin; this filters to
    `dist < margin` so a within-buffer pair means exactly that.

    Args:
        model: The loaded preflight model.
        qpos: A full-model configuration.

    Returns:
        (set[tuple[int, int]]) Each within-margin geom pair, by ordered id key.
    """
    data = model.forward(qpos)
    return {
        _pair_key(int(data.contact[index].geom1), int(data.contact[index].geom2))
        for index in range(int(data.ncon))
        if float(data.contact[index].dist) < model.margin_m
    }


def _first_offbaseline_contact(
    model: PreflightModel, qpos: Sequence[float], allowed: set[tuple[int, int]]
) -> ContactReport | None:
    """Return the closest contact at a configuration that is not an allowed pair.

    Args:
        model: The loaded preflight model.
        qpos: A full-model configuration.
        allowed: Geom pairs within margin at the reference (designed adjacency).

    Returns:
        (ContactReport | None) The smallest-distance off-baseline contact, or None when
        every within-margin pair is allowed.
    """
    data = model.forward(qpos)
    closest: ContactReport | None = None
    for index in range(int(data.ncon)):
        contact = data.contact[index]
        distance = float(contact.dist)
        if distance >= model.margin_m:
            continue
        geom1 = int(contact.geom1)
        geom2 = int(contact.geom2)
        if _pair_key(geom1, geom2) in allowed:
            continue
        if closest is None or distance < closest.dist_m:
            frame = tuple(float(value) for value in contact.frame)
            position = (float(contact.pos[0]), float(contact.pos[1]), float(contact.pos[2]))
            closest = ContactReport(
                geom1=model.geom_name(geom1),
                geom2=model.geom_name(geom2),
                dist_m=distance,
                pos=position,
                frame=frame,
            )
    return closest


def run_preflight(
    trajectory: Sequence[Sequence[float]],
    *,
    requested_margin_m: float | None = None,
    confirmed_zero_margin: bool = False,
    reference_qpos: Sequence[float] | None = None,
) -> PreflightResult:
    """Preflight a trajectory: resolve margin, prove the engine, check density, then walk (①).

    Args:
        trajectory: Waypoints, each a full-model configuration of length `nq`. Build one
            from two arm vectors with `PreflightModel.qpos_from_arms`.
        requested_margin_m: The requested safety margin in metres, or None for the
            `WP-1-06` default (>=0.02 m).
        confirmed_zero_margin: Whether a zero margin was explicitly confirmed (⑤).
        reference_qpos: A collision-free reference configuration whose within-margin pairs
            are treated as designed adjacency; None uses the model's neutral (all zeros).

    Returns:
        (PreflightResult) The verdict with margin, activation, density, and the first
        violating waypoint (index + geoms + distance + position + frame) when not `ok`.

    Raises:
        MarginConfirmationRequiredError: If a zero margin is requested without confirmation
            (⑤, raised by the reused `WP-1-06` policy).
        SelfCollisionInactiveError: If the arm-arm pair test is not live (③ → FAIL_BLOCKING).
        DensityInsufficientError: If the trajectory is too sparse to check without CCD (②).
    """
    margin = resolve_collision_margin(requested_margin_m, confirmed_zero_margin)
    model = PreflightModel(margin.margin_m)
    activation = assert_self_collision_active(model)
    density = require_sufficient_density(trajectory, model.geometry_extents())

    reference = tuple(reference_qpos) if reference_qpos is not None else tuple([0.0] * model.nq)
    allowed = _within_margin_pairs(model, reference)

    for index, waypoint in enumerate(trajectory):
        contact = _first_offbaseline_contact(model, waypoint, allowed)
        if contact is not None:
            return PreflightResult(
                ok=False,
                margin=margin,
                self_collision=activation,
                density=density,
                waypoints_checked=index + 1,
                first_violation=WaypointViolation(waypoint_index=index, contact=contact),
            )

    return PreflightResult(
        ok=True,
        margin=margin,
        self_collision=activation,
        density=density,
        waypoints_checked=len(trajectory),
        first_violation=None,
    )
