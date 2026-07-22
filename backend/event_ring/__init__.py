"""WP-2C-09 — the event ring buffer and the model-error monitor.

Two products for the collision band, both passive and both offline-buildable while
the band's detection default stays OFF (`02b` §3.0):

- **Event ring** (`ring`): a lossless pre/post telemetry window around a collision.
  It reuses the WP-2A-05 audit ring rather than re-implementing it — bind an
  `AuditRingBuffer` and one `on_safety_event` snapshots both, so a stop yields one
  coherent dump of the command/decision window (audit) beside the eight-joint,
  eight-channel physical telemetry `{q, q̇, τ_meas, τ_model, r, ERR, T_MOS, T_Rotor}`
  (`12` FR-SAF-065) this package owns.
- **Model-error monitor** (`monitor`): a per-joint residual moving-average/σ tracker
  that raises a "model needs re-identification" advisory when the safety margin
  shrinks under a payload change or thermal drift (`12` FR-SAF-066).

Boundaries this package keeps: it holds no latch, drives no torque, and is not the
detection activation gate (WP-2C-02). It records unconditionally — a window not kept
is a window that cannot be analysed — and it invents no thresholds; the collision
threshold is the WP-2C-03 calibration output, supplied as input. The on-hardware
claims (a real event at the real loop rate, a real drift) are re-run through
`reverify`, never asserted on synthetic data.
"""

from __future__ import annotations

from backend.event_ring.constants import (
    DEFAULT_POST_EVENT_SEC,
    DEFAULT_PRE_EVENT_SEC,
    EVENT_JOINT_COUNT,
    GRIPPER_JOINT_INDEX,
)
from backend.event_ring.errors import (
    EventRingLossError,
    EventRingShapeError,
    HardwareDeferredError,
)
from backend.event_ring.monitor import (
    DEFAULT_SIGMA_MULTIPLIER,
    JointMargin,
    MarginReport,
    ModelErrorMonitor,
    ModelReidentificationAlert,
)
from backend.event_ring.reverify import (
    FIXTURE_ENV_VAR,
    ReverifyResult,
    fixture_dir_from_env,
    reverify_capture,
    reverify_from_fixture,
)
from backend.event_ring.ring import (
    EventCapture,
    EventDump,
    EventRingBuffer,
)
from backend.event_ring.sample import (
    CHANNEL_COUNT,
    CHANNEL_ORDER,
    EventChannel,
    TelemetrySample,
)

__all__ = [
    "CHANNEL_COUNT",
    "CHANNEL_ORDER",
    "DEFAULT_POST_EVENT_SEC",
    "DEFAULT_PRE_EVENT_SEC",
    "DEFAULT_SIGMA_MULTIPLIER",
    "EVENT_JOINT_COUNT",
    "FIXTURE_ENV_VAR",
    "GRIPPER_JOINT_INDEX",
    "EventCapture",
    "EventChannel",
    "EventDump",
    "EventRingBuffer",
    "EventRingLossError",
    "EventRingShapeError",
    "HardwareDeferredError",
    "JointMargin",
    "MarginReport",
    "ModelErrorMonitor",
    "ModelReidentificationAlert",
    "ReverifyResult",
    "TelemetrySample",
    "fixture_dir_from_env",
    "reverify_capture",
    "reverify_from_fixture",
]
