"""WP-2A-01 — the joint jog producer: continuous/step modes and the `np.linspace` interpolator.

A publish-only source of jog targets for the Wave-1 `ActuationScheduler`. It owns no
CAN handle and no tick: it publishes time-stamped position requests into the
scheduler's latest-wins mailbox, and the scheduler alone writes CAN (I-1).

Public surface:
- `JointJogProducer` — the `Producer` the scheduler swaps in; `publish(target, t_mono)`.
- `plan_step_trajectory` / `plan_continuous_trajectory` — the interpolator that turns
  one step or a continuous hold into a `JogTrajectory` of `np.linspace` waypoints.
- `Arm`, `JogDirection`, `JogAddress` — single-joint addressing into the 16-dim
  bimanual action vector.
- `STEP_SIZES_DEG`, `validate_step_size` — the offered step vocabulary (FR-MAN-010).

Every collaborator the tick depends on — the mailbox, the producer protocol, the
atomic swap — is imported from `backend.actuation`, never re-implemented.
"""

from __future__ import annotations

from backend.jog.addressing import (
    MAX_JOINT_NUMBER,
    MIN_JOINT_NUMBER,
    Arm,
    JogAddress,
    JogDirection,
    validate_step_size,
)
from backend.jog.config import (
    DEFAULT_INTERPOLATION_HZ,
    DEFAULT_STEP_DURATION_SEC,
    STEP_SIZES_DEG,
)
from backend.jog.interpolator import (
    JogTrajectory,
    JogWaypoint,
    frame_count,
    plan_continuous_trajectory,
    plan_step_trajectory,
)
from backend.jog.producer import JointJogProducer

__all__ = [
    "DEFAULT_INTERPOLATION_HZ",
    "DEFAULT_STEP_DURATION_SEC",
    "MAX_JOINT_NUMBER",
    "MIN_JOINT_NUMBER",
    "STEP_SIZES_DEG",
    "Arm",
    "JogAddress",
    "JogDirection",
    "JogTrajectory",
    "JogWaypoint",
    "JointJogProducer",
    "frame_count",
    "plan_continuous_trajectory",
    "plan_step_trajectory",
    "validate_step_size",
]
