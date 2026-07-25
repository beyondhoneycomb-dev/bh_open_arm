"""WP-5-08 — security residual hardening (offline parts) (`14` §3).

This package is the runtime enforcement and composition layer for the residual
security requirements, built on top of the pieces earlier waves already own — it
reuses them, it does not fork them:

- **The one lease.** The FR-OPS-091 command-security token is the *same* object as the
  U-4 deadman lease (`backend.deadman`): `command_lease.CommandGuard` reads the
  generation from the deadman's re-arm handshake and expiry from the deadman's own
  lease clock, adding only per-command-stream anti-replay. There is no second lease.
- **Two-level control lock.** `control_lock` reuses the Wave-0B CAN-fd `flock`
  (`backend.can.lock`) as L1 and adds the single-command-source lock as L2, each
  enforced independently (`FR-OPS-074`/`FR-OPS-075`).
- **Forced release.** `forced_release` engages a safe HOLD before releasing and
  advances the one lease's generation to fence the prior holder (`FR-OPS-076`).
- **Observer mode.** `observer_mode` closes every command path to an observer,
  delegating WS-frame authority to `contracts.ws.authorize_send` (`FR-OPS-077`).
- **Transport security.** `origin_policy` refuses plaintext/wildcard bindings at
  runtime (reusing `contracts.ws.WsSecurityPolicy`) and statically (`FR-OPS-090`).
- **VR source binding.** `vr_source_binding` admits a `:5006` pose only from a
  registered source and pins the isolated-network fallback (`FR-OPS-092`).
- **Dataset upload.** `hub_upload` wires the reused `ops.hubguard` two-step gate
  (`FR-OPS-082`).
- **Device ACL / sandbox.** `device_acl` runs the reused `ops.acl` static checks and
  defers the live cansend-TX-fail check to a re-verification hook (`FR-OPS-029`); the
  live CAN check is never faked green (the ONE RULE).
"""

from __future__ import annotations

from backend.security.command_lease import (
    CommandDecision,
    CommandEnvelope,
    CommandGuard,
    CommandVerdict,
)
from backend.security.control_lock import (
    CommandLockHolder,
    CommandSource,
    CommandSourceLock,
    L2AcquireOutcome,
    L2Refusal,
    TwoLevelControlLock,
)
from backend.security.device_acl import (
    DeviceAclStaticReport,
    LiveCanTxStatus,
    live_can_tx_status,
    reverify_live_can_tx,
    static_config_report,
)
from backend.security.forced_release import (
    ForcedRelease,
    ForcedReleaseError,
    ForceReleaseOutcome,
    ForceReleaseStep,
)
from backend.security.hub_upload import DatasetUploadSecurity
from backend.security.observer_mode import (
    ALL_COMMAND_PATHS,
    CommandPath,
    ObserverWriteError,
    assert_write_authorized,
    may_read,
    observer_refused_paths,
)
from backend.security.origin_policy import (
    ControlChannelSecurity,
    OriginFinding,
    OriginFindingKind,
    OriginPolicyError,
    RestCorsPolicy,
    scan_files,
    scan_python_sources,
    scan_text,
)
from backend.security.vr_source_binding import (
    NetworkIsolationError,
    NetworkIsolationFallback,
    VrAcceptResult,
    VrSource,
    VrSourceBinding,
    VrSourceRefusal,
    VrSourceRegistry,
)

__all__ = [
    "ALL_COMMAND_PATHS",
    "CommandDecision",
    "CommandEnvelope",
    "CommandGuard",
    "CommandLockHolder",
    "CommandPath",
    "CommandSource",
    "CommandSourceLock",
    "CommandVerdict",
    "ControlChannelSecurity",
    "DatasetUploadSecurity",
    "DeviceAclStaticReport",
    "ForceReleaseOutcome",
    "ForceReleaseStep",
    "ForcedRelease",
    "ForcedReleaseError",
    "L2AcquireOutcome",
    "L2Refusal",
    "LiveCanTxStatus",
    "NetworkIsolationError",
    "NetworkIsolationFallback",
    "ObserverWriteError",
    "OriginFinding",
    "OriginFindingKind",
    "OriginPolicyError",
    "RestCorsPolicy",
    "TwoLevelControlLock",
    "VrAcceptResult",
    "VrSource",
    "VrSourceBinding",
    "VrSourceRefusal",
    "VrSourceRegistry",
    "assert_write_authorized",
    "live_can_tx_status",
    "may_read",
    "observer_refused_paths",
    "reverify_live_can_tx",
    "scan_files",
    "scan_python_sources",
    "scan_text",
    "static_config_report",
]
