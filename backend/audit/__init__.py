"""WP-2A-05 — the audit ring buffer: the pre-conversion request preserved, on-stop dump.

A time-bounded window (default 10 s) recording the SPINE §6 action-side audit channels
per tick — `requestedPositionAction` and `acceptedPositionAction` (the Wave-1 `GateFrame`
pair, both mandatory), `executedMitCommand`, `safetyOverride` with its clamp reason and
stale/latch flags — plus the calibration transform chain that makes an offset double-add
or miss detectable and blockable on the spot.

Public surface: consumers import the ring, its record and dump types, and the offset
integrity primitives from here. The ring holds no latch of its own; it consumes
`CTR-ACT@v1` and reuses `backend.actuation`'s `GateFrame` recording rule and the
`ops.cancel` `LatchReason` latch contract. The physical-telemetry event ring
(`q̇, τ_meas, …`, `12` FR-SAF-065) is the downstream WP-2C-09 concern, not this package.
"""

from __future__ import annotations

from backend.audit.record import AuditRecord
from backend.audit.ring import (
    DEFAULT_HORIZON_SEC,
    AuditDump,
    AuditRingBuffer,
)
from backend.audit.transform import (
    DECISION_A_OFFSET_APPLICATIONS,
    OFFSET_RESIDUAL_TOLERANCE_RAD,
    JointTransform,
    OffsetFault,
    OffsetIntegrityError,
    OffsetVerdict,
    check_chain,
    check_joint,
)

__all__ = [
    "DECISION_A_OFFSET_APPLICATIONS",
    "DEFAULT_HORIZON_SEC",
    "OFFSET_RESIDUAL_TOLERANCE_RAD",
    "AuditDump",
    "AuditRecord",
    "AuditRingBuffer",
    "JointTransform",
    "OffsetFault",
    "OffsetIntegrityError",
    "OffsetVerdict",
    "check_chain",
    "check_joint",
]
