"""Full-trajectory pre-verify before replay (WP-2D-06 ①).

The pre-verify walks the dense trajectory and refuses replay unless every sample clears four
checks — position limit, joint velocity, self-collision, and environment-collision — reporting
the FIRST violating waypoint index (`02b` WP-2D-06 ①). The two collision checks are NOT
re-implemented here: they are `WP-2C-08` (`backend.collision_preflight.run_preflight`), which
drives each sample's full-model configuration through `mj_forward` on the committed bimanual
asset and gates itself on the margin policy, the self-collision activation proof, and the
waypoint-density rule. This band adds only the limit and velocity walks, whose ceilings are
their single canonical sources (`sim.ik` soft limits, the `WP-1-06` velocity canon), and folds
all four verdicts into one first-violation report.

There is no verdict that bypasses a check: `run_pre_verify` runs all four unconditionally and a
replay is built only from an `ok` result (`backend.replay.replay.build_replay`), so a
pre-verify bypass path — the `FAIL_BLOCKING` branch of `02b` WP-2D-06 — does not exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np

from backend.collision_preflight.model import PreflightModel, geom_arm_side
from backend.collision_preflight.preflight import PreflightResult, run_preflight
from backend.replay.constants import LIMIT_TOLERANCE_RAD
from backend.replay.interpolate import InterpolatedTrajectory
from backend.safety_bringup.constants import ARM_JOINT_COUNT, GRIPPER_SPEED_CLAMP_RAD_S
from backend.safety_bringup.velocity import bootstrap_limiter_rad_s
from sim.ik.limits import soft_limits

# The velocity of one grid step could sit numerically on the ceiling after auto-extension; a
# tiny slack keeps that boundary case from reading as a violation while still catching a genuine
# overspeed. Radians per second.
VELOCITY_TOLERANCE_RAD_S = 1e-9


class PreVerifyCategory(Enum):
    """Which of the four checks a first violation belongs to (`02b` WP-2D-06 ①)."""

    LIMIT = "limit"
    VELOCITY = "velocity"
    SELF_COLLISION = "self_collision"
    ENV_COLLISION = "env_collision"


@dataclass(frozen=True)
class PreVerifyResult:
    """The verdict of the four-check pre-verify over one trajectory.

    Attributes:
        ok: True when no sample violated any of the four checks.
        category: The check the first violation belongs to, or None when `ok`.
        first_violation_index: Zero-based index of the first violating sample, or None.
        detail: Human-readable context for the operator log.
        collision: The reused `WP-2C-08` preflight verdict (its own evidence record).
        residual_note: The linear-profile residual-pollution note (④), or "".
    """

    ok: bool
    category: PreVerifyCategory | None
    first_violation_index: int | None
    detail: str
    collision: PreflightResult
    residual_note: str


def velocity_limits_rad_s() -> np.ndarray:
    """Return the per-joint velocity ceiling for the eight replay joints.

    The seven arm joints take the `WP-1-06` bootstrap velocity canon (the three-way physical
    minimum overlaid with the velocity cap); the gripper takes its register clamp. Both come
    from `backend.safety_bringup`, so the ceiling has one source, not a copy here.

    Returns:
        (np.ndarray) Shape (8,): seven arm ceilings then the gripper ceiling, radians/second.
    """
    return np.concatenate(
        [np.asarray(bootstrap_limiter_rad_s(), dtype=float), [GRIPPER_SPEED_CLAMP_RAD_S]]
    )


def density_step_ceiling_rad(requested_margin_m: float | None = None) -> float:
    """Return the `WP-2C-08` per-step joint displacement ceiling for the committed model.

    This is the density rule's `min_link_thickness / max_link_radius`: the largest joint step
    the geometry admits between two waypoints without a link tunnelling a collision the
    discrete samples never see. The interpolator's auto-extension holds every step below it.

    Args:
        requested_margin_m: The collision margin the model is loaded with; None uses the
            `WP-1-06` default. The value does not affect geometry extents, only contact
            generation, so any resolved margin yields the same ceiling.

    Returns:
        (float) The per-step joint displacement ceiling, radians.
    """
    margin = requested_margin_m if requested_margin_m is not None else 0.0
    extents = PreflightModel(margin).geometry_extents()
    return extents.min_link_thickness_m / extents.max_link_radius_m


def _limit_bounds(side: str) -> tuple[np.ndarray, np.ndarray]:
    """Return the lower and upper soft limits for the eight joints of one arm.

    Args:
        side: `"right"` or `"left"`.

    Returns:
        (np.ndarray) Lower bounds, shape (8,): seven arm joints then gripper, radians.
        upper (np.ndarray) Upper bounds, shape (8,).
    """
    limits = soft_limits(side)[: ARM_JOINT_COUNT + 1]
    lowers = np.asarray([limit.lower_rad.value for limit in limits], dtype=float)
    uppers = np.asarray([limit.upper_rad.value for limit in limits], dtype=float)
    return lowers, uppers


def _first_true_row(mask: np.ndarray) -> int | None:
    """Return the first row index that holds any True, or None.

    Args:
        mask: A boolean array, shape (N, K).

    Returns:
        (int | None) The smallest row index with a True, or None when none.
    """
    rows = np.nonzero(mask.any(axis=1))[0]
    return int(rows[0]) if rows.size else None


def _limit_violation(traj: InterpolatedTrajectory) -> tuple[int | None, str]:
    """Find the first sample whose eight joints leave the soft limits.

    Args:
        traj: The dense trajectory.

    Returns:
        (int | None) The first violating sample index, or None.
        detail (str) The offending joints at that sample, or "".
    """
    lowers, uppers = _limit_bounds(traj.arm_side)
    full = np.column_stack([traj.arm, traj.gripper])
    outside = (full < lowers - LIMIT_TOLERANCE_RAD) | (full > uppers + LIMIT_TOLERANCE_RAD)
    index = _first_true_row(outside)
    if index is None:
        return None, ""
    joints = [int(joint) for joint in np.nonzero(outside[index])[0]]
    return index, f"joints {joints} outside soft limits at sample {index}"


def _velocity_violation(traj: InterpolatedTrajectory) -> tuple[int | None, str]:
    """Find the first sample reached at more than a joint's velocity ceiling.

    v2.0 declares no acceleration limits, so only velocity is bounded here; the linear
    profile's velocity discontinuity is surfaced by the residual note (④), not by an
    acceleration check that the joint model does not carry.

    Args:
        traj: The dense trajectory.

    Returns:
        (int | None) The first violating sample index (the later of the two samples), or None.
        detail (str) The offending joints and their velocities, or "".
    """
    if len(traj) < 2:
        return None, ""
    limits = velocity_limits_rad_s()
    full = np.column_stack([traj.arm, traj.gripper])
    velocity = np.abs(np.diff(full, axis=0)) * traj.rate_hz
    over = velocity > limits + VELOCITY_TOLERANCE_RAD_S
    row = _first_true_row(over)
    if row is None:
        return None, ""
    index = row + 1
    joints = [int(joint) for joint in np.nonzero(over[row])[0]]
    return index, f"joints {joints} exceed velocity ceiling at sample {index}"


def _collision_category(preflight: PreflightResult) -> PreVerifyCategory:
    """Classify a preflight violation as self-collision or environment-collision.

    Args:
        preflight: A non-ok preflight result with a first violation.

    Returns:
        (PreVerifyCategory) SELF_COLLISION when both offending geoms are arm geoms, else
        ENV_COLLISION (an arm against the cell).
    """
    contact = preflight.first_violation.contact
    if geom_arm_side(contact.geom1) and geom_arm_side(contact.geom2):
        return PreVerifyCategory.SELF_COLLISION
    return PreVerifyCategory.ENV_COLLISION


def run_pre_verify(
    traj: InterpolatedTrajectory,
    requested_margin_m: float | None = None,
    confirmed_zero_margin: bool = False,
    reference_qpos: list[float] | None = None,
) -> PreVerifyResult:
    """Walk a trajectory through all four checks and report the first violation (①).

    Every check runs; the earliest violating sample across limit, velocity, and collision is
    reported, ties resolved limit-first then velocity then collision. The collision walk is the
    reused `WP-2C-08` preflight over the full-model configuration of each sample (the moving arm
    interpolated, the other arm held).

    Args:
        traj: The dense trajectory to verify.
        requested_margin_m: Collision margin in metres, or None for the `WP-1-06` default.
        confirmed_zero_margin: Whether a zero margin was explicitly confirmed.
        reference_qpos: A collision-free reference configuration; None uses the model neutral,
            so the trajectory's own start is never trusted as safe by assumption.

    Returns:
        (PreVerifyResult) The combined verdict; `ok` only when all four checks pass on every
        sample.
    """
    model = PreflightModel(requested_margin_m if requested_margin_m is not None else 0.0)
    qpos_trajectory = [list(_full_qpos(model, traj, sample)) for sample in range(len(traj))]
    collision = run_preflight(
        qpos_trajectory,
        requested_margin_m=requested_margin_m,
        confirmed_zero_margin=confirmed_zero_margin,
        reference_qpos=reference_qpos,
    )

    limit_index, limit_detail = _limit_violation(traj)
    velocity_index, velocity_detail = _velocity_violation(traj)
    collision_index = None if collision.ok else collision.first_violation.waypoint_index

    candidates: list[tuple[int, PreVerifyCategory, str]] = []
    if limit_index is not None:
        candidates.append((limit_index, PreVerifyCategory.LIMIT, limit_detail))
    if velocity_index is not None:
        candidates.append((velocity_index, PreVerifyCategory.VELOCITY, velocity_detail))
    if collision_index is not None:
        candidates.append(
            (
                collision_index,
                _collision_category(collision),
                f"collision at sample {collision_index}: "
                f"{collision.first_violation.contact.geom1} vs "
                f"{collision.first_violation.contact.geom2}",
            )
        )

    residual_note = traj.residual_ui_note()
    if not candidates:
        return PreVerifyResult(
            ok=True,
            category=None,
            first_violation_index=None,
            detail="",
            collision=collision,
            residual_note=residual_note,
        )

    index, category, detail = min(candidates, key=_candidate_order)
    return PreVerifyResult(
        ok=False,
        category=category,
        first_violation_index=index,
        detail=detail,
        collision=collision,
        residual_note=residual_note,
    )


# The tie-break order among coincident first violations: earliest sample wins, then limit
# before velocity before either collision class, so one trajectory yields one deterministic
# report regardless of check evaluation order.
_CATEGORY_RANK = {
    PreVerifyCategory.LIMIT: 0,
    PreVerifyCategory.VELOCITY: 1,
    PreVerifyCategory.SELF_COLLISION: 2,
    PreVerifyCategory.ENV_COLLISION: 3,
}


def _candidate_order(candidate: tuple[int, PreVerifyCategory, str]) -> tuple[int, int]:
    """Key a `(index, category, detail)` candidate by sample index then category rank.

    Args:
        candidate: The first-violation candidate from one check.

    Returns:
        (tuple[int, int]) The sample index and the category's tie-break rank.
    """
    index, category, _ = candidate
    return index, _CATEGORY_RANK[category]


def _full_qpos(
    model: PreflightModel, traj: InterpolatedTrajectory, sample: int
) -> tuple[float, ...]:
    """Build one sample's full-model configuration: moving arm interpolated, other held.

    Args:
        model: The loaded preflight model, used only for its name-addressed qpos assembly.
        traj: The dense trajectory.
        sample: The sample index.

    Returns:
        (tuple[float, ...]) A configuration of length `nq` for `run_preflight`.
    """
    moving = traj.arm[sample]
    held = traj.other_arm_hold
    if traj.arm_side == "right":
        return model.qpos_from_arms(held, moving)
    return model.qpos_from_arms(moving, held)
