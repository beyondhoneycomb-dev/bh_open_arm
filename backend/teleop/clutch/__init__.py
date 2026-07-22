"""Teleop pose conditioning — clutch, scale, One Euro smoother, align ramp (WP-3B-09).

The reusable primitives the teleop safety state machine (`WP-3B-10`) wires together,
built on the frozen `CTR-TEL@v1` contract and exercised against synthetic VR frames,
never a headset. Each maps to a `05` §3 requirement:

- `ClutchGate` — the deadman with the pose reference latch: release discards the
  reference, re-grip re-captures it, so the re-grip delta starts at zero (`FR-TEL-030`/
  `031`).
- `DeltaScaler` — relative-delta mapping with position and rotation scale as independent
  factors (`FR-TEL-029`/`032`/`033`).
- `OneEuroPoseSmoother` — adaptive-cutoff position + SLERP rotation, with the `reset()`
  that suppresses re-entry jumps (`FR-TEL-039`/`040`).
- `AlignRamp` — the alignment ramp as a per-second rate whose per-frame step is derived
  as `align_rate_rad_s / fps`, never a per-frame constant (`FR-TEL-083`).
- `TeleopPoseConditioner` — wires the above and is the single place that decides when the
  smoother resets (INVALID->valid and re-engage), so the invariant is observable.

This tree consumes the VR source interface (`PoseSource` / `VrFrame`) from
`backend.teleop.vr_udp` (`WP-3B-07`) by import and the tracking-validity enum from the
frozen `contracts.teleop`, redefining neither and re-implementing no reception or
transform; it touches no CAN, actuation or contract module.
"""

from __future__ import annotations

from backend.teleop.clutch.align import AlignRamp
from backend.teleop.clutch.clutch import ClutchEvent, ClutchGate, PoseReference
from backend.teleop.clutch.conditioner import (
    ConditionResult,
    TeleopPoseConditioner,
    ValidityTracker,
)
from backend.teleop.clutch.scale import DeltaScaler, PoseTarget
from backend.teleop.clutch.smoother import OneEuroPoseSmoother

__all__ = [
    "AlignRamp",
    "ClutchEvent",
    "ClutchGate",
    "ConditionResult",
    "DeltaScaler",
    "OneEuroPoseSmoother",
    "PoseReference",
    "PoseTarget",
    "TeleopPoseConditioner",
    "ValidityTracker",
]
