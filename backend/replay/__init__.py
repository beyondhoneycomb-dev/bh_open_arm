"""Interpolator, replay, and pre-verify (WP-2D-06).

This band turns a sparse teaching sequence into a dense, pre-verified trajectory and steps it
under operator and deadman control. It builds the interpolators and the safety checker itself
(`02b` WP-2D-06: LeRobot's `robots/` tree has no `interpolate`/`smooth_move`/`trajectory`), but
it reuses rather than re-implements the two guarantees that already exist:

- the collision pre-verify is `WP-2C-08` (`backend.collision_preflight.run_preflight`) — self-
  and environment-collision over the committed bimanual asset;
- the deadman abort is `WP-2A-02` (`backend.deadman.DeadmanMonitor`) — the live-then-released
  edge that latches motion to a one-way hold.

The velocity ceilings are the `WP-1-06` canon and the position limits are `sim.ik`'s soft
limits, so no physical bound is redefined here. `build_replay` is the sole entry to a runnable
executor and runs the full pre-verify first, so a pre-verify bypass path does not exist.
"""

from __future__ import annotations

from backend.replay.constants import (
    DEFAULT_RATE_HZ,
    DEFAULT_SEGMENT_DURATION_S,
    LINEAR_RESIDUAL_UI_NOTE,
)
from backend.replay.interpolate import (
    InterpolatedTrajectory,
    SegmentPlan,
    ease,
    interpolate_trajectory,
)
from backend.replay.preverify import (
    PreVerifyCategory,
    PreVerifyResult,
    density_step_ceiling_rad,
    run_pre_verify,
    velocity_limits_rad_s,
)
from backend.replay.replay import (
    PreVerifyError,
    ReplayExecutor,
    ReplaySample,
    ReplayState,
    build_replay,
)
from backend.replay.teaching import (
    ZeroMatchBlockedError,
    build_replay_from_points,
    spec_from_teaching_points,
    waypoint_from_teaching_point,
)
from backend.replay.waypoint import (
    InterpolationMethod,
    ReplayWaypoint,
    TrajectorySpec,
    dwell_sample_count,
)

__all__ = [
    "DEFAULT_RATE_HZ",
    "DEFAULT_SEGMENT_DURATION_S",
    "LINEAR_RESIDUAL_UI_NOTE",
    "InterpolatedTrajectory",
    "InterpolationMethod",
    "PreVerifyCategory",
    "PreVerifyError",
    "PreVerifyResult",
    "ReplayExecutor",
    "ReplaySample",
    "ReplayState",
    "ReplayWaypoint",
    "SegmentPlan",
    "TrajectorySpec",
    "ZeroMatchBlockedError",
    "build_replay",
    "build_replay_from_points",
    "density_step_ceiling_rad",
    "dwell_sample_count",
    "ease",
    "interpolate_trajectory",
    "run_pre_verify",
    "spec_from_teaching_points",
    "velocity_limits_rad_s",
    "waypoint_from_teaching_point",
]
