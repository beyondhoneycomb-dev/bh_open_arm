"""Dataset upload security — push_to_hub demands confirm + audit (`FR-OPS-082`).

`FR-OPS-082` makes a Hub upload legal only after two steps: an explicit per-upload
confirmation and an audit-log entry, with `push_to_hub` defaulting to False as a code
path (not merely a config default), on pain of `OA-DAT-005`. That whole enforcement
already exists in `ops.hubguard` (`WP-OPS-04`): the default-flip, the two-step gate,
and the audit-before-upload ordering. This module does not re-implement it — it wires
`HubGuard` as the WP-5-08 dataset-upload security surface, so the residual-hardening
band has one entry point and `CG-5-08i` exercises the real enforcement.
"""

from __future__ import annotations

from pathlib import Path

from ops.hubguard.audit import UploadAuditLog, UploadTarget
from ops.hubguard.push_policy import (
    HubGuard,
    UploadConfirmation,
    UploadDecision,
    Uploader,
)


class DatasetUploadSecurity:
    """The WP-5-08 upload gate: a thin wiring of the reused `ops.hubguard` guard.

    Ownership: owns the `HubGuard` (and, through it, the sole append-only audit log
    writer). `request_upload` is the only path that can act on `push_to_hub=True`, and
    it audits before it uploads, both inherited from `HubGuard.run` — so an upload with
    no audit line is unreachable, not merely discouraged.
    """

    def __init__(self, audit_log_path: Path) -> None:
        """Wire the guard onto an append-only audit log at the given path.

        Args:
            audit_log_path: Where confirmed uploads are recorded (JSONL, append-only).
        """
        self._guard = HubGuard(UploadAuditLog(audit_log_path))

    def request_upload(
        self,
        requested: bool | None,
        confirmation: UploadConfirmation | None,
        uploader: Uploader,
    ) -> UploadDecision:
        """Resolve an upload request through the two-step gate, auditing on approval.

        Args:
            requested: The user's `push_to_hub` value — None when unspecified, which
                the policy resolves to False (the upstream True is overridden).
            confirmation: The explicit per-upload confirmation, or None when absent.
            uploader: The upload side effect, run only for an authorised upload.

        Returns:
            (UploadDecision) The resolved decision. The uploader ran iff
            `push_to_hub` is True, in which case exactly one audit entry was written
            first.
        """
        return self._guard.run(requested, confirmation, uploader)


__all__ = [
    "DatasetUploadSecurity",
    "UploadConfirmation",
    "UploadDecision",
    "UploadTarget",
    "Uploader",
]
