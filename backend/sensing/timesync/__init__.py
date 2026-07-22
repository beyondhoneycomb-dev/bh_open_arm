"""Time synchronisation for multi-camera capture (WP-3B-04, `02b` §6).

`02b` §6.1/§6.2 WP-3B-04: pair frames across camera slots by nearest capture time
within a configurable `slop`, and when a slot has no frame within slop, **drop** — no
interpolation, no duplication, because a fabricated frame is the defect. This package
is that synchroniser plus the RealSense master/slave hardware-sync model and the
session-drift check.

The layers:

- `policy` — the frozen `ApproximateTime` policy: `slop`/`queue_size`, the fps-derived
  slop floor (half the frame interval), and the arrival-time fallbacks that stay off
  by contract.
- `frame` — the `TimedFrame` the matcher pairs, and the matching *basis*: sensor
  timestamp when the device exposes one, else the grab-site `capture_ts`.
- `synchronizer` — the nearest-match, drop-on-miss engine; a match miss is a COUNTED
  drop (`CTR-CAP@v1`), never a synthesised frame.
- `hwsync` — the RealSense `inter_cam_sync_mode` group: one master, the rest slaves,
  and one fps forced across every stream.
- `drift` — session start-vs-end q99 comparison, reusing the frozen
  `backend.camera.syncslop` distribution rather than a second slop definition.
- `reverify` — the deferred hook that re-runs the slop/drift check over a real
  RealSense capture, gated behind `OPENARM_TIMESYNC_REAL_FIXTURE`.

Every time-, camera- and queue-shaped value is consumed from `CTR-PRIM@v1` /
`CTR-CAP@v1` / `CTR-CAM@v1` and never restated here (`02b` §5.0b).
"""

from __future__ import annotations

from backend.sensing.timesync.drift import DriftReport, session_drift
from backend.sensing.timesync.frame import TimedFrame, match_timestamp, timed_from_capture
from backend.sensing.timesync.hwsync import (
    HardwareSyncError,
    HardwareSyncGroup,
    HardwareSyncMember,
    SyncRole,
    enforce_same_fps,
    inter_cam_sync_mode_value,
)
from backend.sensing.timesync.policy import (
    SyncPolicy,
    SyncPolicyError,
    default_queue_size,
    slop_floor_ns,
)
from backend.sensing.timesync.reverify import (
    DriftVerifyResult,
    fixture_dir_from_env,
    reverify_from_fixture,
)
from backend.sensing.timesync.synchronizer import (
    DropTally,
    MatchedSet,
    SyncResult,
    synchronize,
)

__all__ = [
    "DriftReport",
    "DriftVerifyResult",
    "DropTally",
    "HardwareSyncError",
    "HardwareSyncGroup",
    "HardwareSyncMember",
    "MatchedSet",
    "SyncPolicy",
    "SyncPolicyError",
    "SyncResult",
    "SyncRole",
    "TimedFrame",
    "default_queue_size",
    "enforce_same_fps",
    "fixture_dir_from_env",
    "inter_cam_sync_mode_value",
    "match_timestamp",
    "reverify_from_fixture",
    "session_drift",
    "slop_floor_ns",
    "synchronize",
    "timed_from_capture",
]
