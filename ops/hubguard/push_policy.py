"""push_to_hub default enforcement — the code path that flips the upstream True.

Spec 16 §11 trap 3 and FR-OPS-082: LeRobot's `RecordConfig.push_to_hub` defaults
to `True`, so an unspecified value silently uploads in-house data to the HF Hub.
The 02a §6 contract is precise about the shape of the fix — the default-false is a
CODE PATH, not a config default: an unspecified value resolves to False here, and
reaching True demands BOTH an explicit request and a per-upload user confirmation,
with an audit entry written as the upload is granted. No single config key yields
an upload on its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ops.hubguard.audit import UploadAuditLog, UploadTarget

# The value LeRobot binds `RecordConfig.push_to_hub` to when the user says nothing
# (16 §11 trap 3). Named so the flip in `resolve_push_to_hub` is legible and the
# regression test can assert the upstream premise it is written to overturn.
UPSTREAM_PUSH_TO_HUB_DEFAULT = True
# What an unspecified value resolves to under this policy — the flip itself.
ENFORCED_PUSH_TO_HUB_DEFAULT = False


@dataclass(frozen=True)
class UploadConfirmation:
    """An explicit, per-upload user confirmation — step 1 of the 2-step gate.

    Presence of this object is the user assertion "yes, upload this dataset to this
    target, as me". Absence means no confirmation was given, which forces the local
    path regardless of any config value.
    """

    who: str
    dataset: str
    target: UploadTarget


@dataclass(frozen=True)
class RecordConfigView:
    """The push-relevant slice of LeRobot's `RecordConfig`.

    `push_to_hub` is `bool | None`, where None means the user did not specify it.
    The upstream config binds the same field to True by default; capturing the
    unspecified case as None is what lets the wrapper separate "user asked to
    upload" from "user said nothing" — the whole point of FR-OPS-082.
    """

    push_to_hub: bool | None


@dataclass(frozen=True)
class UploadDecision:
    """The resolved push_to_hub value plus why it was resolved that way.

    Attributes:
        push_to_hub: The effective value handed to LeRobot.
        suppressed: True when an upload was requested but blocked for lack of a
            confirmation — a non-silent signal so a caller/GUI can prompt for the
            missing step rather than a value that just quietly reads False.
        reason: Human-readable justification for the resolved value.
    """

    push_to_hub: bool
    suppressed: bool
    reason: str


def authorize_upload(
    requested: bool | None,
    confirmation: UploadConfirmation | None,
) -> UploadDecision:
    """Resolve the effective push_to_hub value from a request and a confirmation.

    This is a pure decision with no side effects; `HubGuard.run` performs the audit
    write and the upload. It is the single place that may return
    `push_to_hub=True`, and it does so only when a request AND a confirmation are
    both present.

    Args:
        requested: The push_to_hub the user asked for — None when unspecified.
        confirmation: The per-upload confirmation, or None when absent.

    Returns:
        (UploadDecision) The resolved value with its rationale.
    """
    if requested is None:
        return UploadDecision(
            push_to_hub=ENFORCED_PUSH_TO_HUB_DEFAULT,
            suppressed=False,
            reason="push_to_hub unspecified; local default enforced (upstream True overridden)",
        )
    if not requested:
        return UploadDecision(
            push_to_hub=False,
            suppressed=False,
            reason="push_to_hub explicitly disabled",
        )
    if confirmation is None:
        return UploadDecision(
            push_to_hub=False,
            suppressed=True,
            reason="upload requested without confirmation; suppressed to prevent unaudited upload",
        )
    return UploadDecision(
        push_to_hub=True,
        suppressed=False,
        reason="upload confirmed",
    )


def resolve_push_to_hub(
    view: RecordConfigView,
    confirmation: UploadConfirmation | None,
) -> UploadDecision:
    """Apply the push_to_hub policy to a record-config view.

    This is the forcing wrapper named in the 02a §6 acceptance ①: it takes the
    config as the user left it (with `push_to_hub` possibly unspecified) and returns
    the enforced value, flipping the upstream True default to False.

    Args:
        view: The push-relevant slice of the record config.
        confirmation: The per-upload confirmation, or None when absent.

    Returns:
        (UploadDecision) The resolved value with its rationale.
    """
    return authorize_upload(view.push_to_hub, confirmation)


class Uploader(Protocol):
    """The network side effect an authorised upload performs.

    Injected so the guard's authorisation logic is exercised without a live Hub
    push, and so the sole caller of a real upload is this guard.
    """

    def __call__(self, dataset: str, target: UploadTarget) -> None: ...


class HubGuard:
    """Single enforcement point for the push_to_hub 2-step gate.

    Ownership: holds the sole `UploadAuditLog` writer. `run` is the only path that
    acts on `push_to_hub=True`, and it writes the audit entry BEFORE invoking the
    uploader — so an upload with no audit line is unreachable through this API
    rather than merely discouraged. That ordering is the real lock: the audit
    record of intent survives even if the upload then fails.
    """

    def __init__(self, audit_log: UploadAuditLog) -> None:
        self._audit = audit_log

    def run(
        self,
        requested: bool | None,
        confirmation: UploadConfirmation | None,
        uploader: Uploader,
    ) -> UploadDecision:
        """Authorise, and on approval audit-then-upload, exactly once.

        Args:
            requested: The push_to_hub the user asked for — None when unspecified.
            confirmation: The per-upload confirmation, or None when absent.
            uploader: The side effect to run only for an authorised upload.

        Returns:
            (UploadDecision) The resolved decision. The uploader ran iff
            `push_to_hub` is True, in which case exactly one audit entry was
            written first.
        """
        decision = authorize_upload(requested, confirmation)
        if decision.push_to_hub and confirmation is not None:
            self._audit.record(confirmation.who, confirmation.dataset, confirmation.target)
            uploader(confirmation.dataset, confirmation.target)
        return decision
