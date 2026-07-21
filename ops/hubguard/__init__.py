"""WP-OPS-04 — push_to_hub=false enforcement, upload audit, bind and port policy.

Four independent guards that share one discipline: a data-leaking or
network-exposing default is made safe as a CODE PATH, and undoing it demands an
explicit user step.

- `push_policy` — flips LeRobot's upstream `push_to_hub=True` to False and gates
  any upload behind confirmation-plus-audit (FR-OPS-082, 16 §11 trap 3).
- `audit` — the append-only {who, when, dataset, target} upload trail.
- `binding` — services bind loopback by default; non-local exposure needs
  confirmation (FR-SYS-026).
- `portclash` — startup refuses on a duplicate or already-held port
  (FR-SYS-026, §2.17 web-backend/openpi 8000 collision).
"""

from __future__ import annotations

from ops.hubguard.audit import AuditEntry, UploadAuditLog, UploadTarget
from ops.hubguard.binding import (
    DEFAULT_BIND_HOST,
    LOCAL_HOSTS,
    NonLocalBindingError,
    is_local,
    resolve_bind_host,
)
from ops.hubguard.portclash import (
    DEFAULT_PORT_MAP,
    ClashSource,
    PortClash,
    PortClashError,
    ServiceEndpoint,
    bind_clashes,
    manifest_clashes,
    verify_startup,
)
from ops.hubguard.push_policy import (
    ENFORCED_PUSH_TO_HUB_DEFAULT,
    UPSTREAM_PUSH_TO_HUB_DEFAULT,
    HubGuard,
    RecordConfigView,
    UploadConfirmation,
    UploadDecision,
    Uploader,
    authorize_upload,
    resolve_push_to_hub,
)

__all__ = [
    "DEFAULT_BIND_HOST",
    "DEFAULT_PORT_MAP",
    "ENFORCED_PUSH_TO_HUB_DEFAULT",
    "LOCAL_HOSTS",
    "UPSTREAM_PUSH_TO_HUB_DEFAULT",
    "AuditEntry",
    "ClashSource",
    "HubGuard",
    "NonLocalBindingError",
    "PortClash",
    "PortClashError",
    "RecordConfigView",
    "ServiceEndpoint",
    "UploadAuditLog",
    "UploadConfirmation",
    "UploadDecision",
    "UploadTarget",
    "Uploader",
    "authorize_upload",
    "bind_clashes",
    "is_local",
    "manifest_clashes",
    "resolve_bind_host",
    "resolve_push_to_hub",
    "verify_startup",
]
