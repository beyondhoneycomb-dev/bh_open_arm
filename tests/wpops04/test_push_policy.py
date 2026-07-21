"""WP-OPS-04 acceptance ①②③ — push_to_hub default flip, no-confirmation
suppression, and the audit entry a confirmed upload emits.

The 02a §6 contract: default-false is a code path, and reaching an actual upload
requires an explicit request AND a per-upload confirmation, with exactly one audit
line written as it is granted.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from ops.hubguard.audit import UploadAuditLog, UploadTarget
from ops.hubguard.push_policy import (
    ENFORCED_PUSH_TO_HUB_DEFAULT,
    UPSTREAM_PUSH_TO_HUB_DEFAULT,
    HubGuard,
    RecordConfigView,
    UploadConfirmation,
    authorize_upload,
    resolve_push_to_hub,
)
from tests.wpops04.doubles import FixedClock, RecordingUploader

_TARGET = UploadTarget(repo_id="pick-place-v3", private=True, account="acme-robotics")
_MOMENT = datetime(2026, 7, 22, 12, 0, 0, tzinfo=UTC)


def _confirmation() -> UploadConfirmation:
    return UploadConfirmation(who="operator@acme", dataset="pick-place-v3", target=_TARGET)


# --- Acceptance ① : unspecified push_to_hub resolves False, flipping upstream True.


def test_upstream_default_is_the_true_this_policy_overrides() -> None:
    # The premise the wrapper exists to reverse; if upstream ever ships False this
    # constant must change and this test is the tripwire.
    assert UPSTREAM_PUSH_TO_HUB_DEFAULT is True


def test_unspecified_push_to_hub_resolves_false() -> None:
    decision = resolve_push_to_hub(RecordConfigView(push_to_hub=None), confirmation=None)
    assert decision.push_to_hub is ENFORCED_PUSH_TO_HUB_DEFAULT is False
    assert decision.suppressed is False


def test_explicit_false_stays_false() -> None:
    decision = resolve_push_to_hub(RecordConfigView(push_to_hub=False), confirmation=None)
    assert decision.push_to_hub is False


# --- Acceptance ② : push_to_hub=true with no confirmation performs zero uploads.


def test_requested_true_without_confirmation_uploads_nothing(tmp_path: Path) -> None:
    audit = UploadAuditLog(tmp_path / "audit.jsonl")
    guard = HubGuard(audit)
    uploader = RecordingUploader()

    decision = guard.run(requested=True, confirmation=None, uploader=uploader)

    assert decision.push_to_hub is False
    assert decision.suppressed is True
    assert uploader.count == 0
    assert audit.entries() == []


def test_authorize_true_without_confirmation_is_suppressed() -> None:
    decision = authorize_upload(requested=True, confirmation=None)
    assert decision.push_to_hub is False
    assert decision.suppressed is True


# --- Acceptance ③ : a confirmed upload emits exactly one {who,when,dataset,target}.


def test_confirmed_upload_emits_one_audit_entry(tmp_path: Path) -> None:
    audit = UploadAuditLog(tmp_path / "audit.jsonl", clock=FixedClock(_MOMENT))
    guard = HubGuard(audit)
    uploader = RecordingUploader()

    decision = guard.run(requested=True, confirmation=_confirmation(), uploader=uploader)

    assert decision.push_to_hub is True
    assert uploader.count == 1

    entries = audit.entries()
    assert len(entries) == 1
    entry = entries[0]
    assert entry.who == "operator@acme"
    assert entry.when == _MOMENT.isoformat()
    assert entry.dataset == "pick-place-v3"
    assert entry.target == _TARGET


def test_audit_precedes_upload_so_a_true_decision_always_has_a_record(tmp_path: Path) -> None:
    # The real lock: the only path that uploads also writes the audit line first,
    # so an authorised upload with no record is unreachable, not merely rare.
    audit = UploadAuditLog(tmp_path / "audit.jsonl", clock=FixedClock(_MOMENT))
    guard = HubGuard(audit)
    uploader = RecordingUploader()

    guard.run(requested=True, confirmation=_confirmation(), uploader=uploader)

    assert len(audit.entries()) == uploader.count == 1


def test_repeated_confirmed_uploads_each_get_their_own_entry(tmp_path: Path) -> None:
    audit = UploadAuditLog(tmp_path / "audit.jsonl", clock=FixedClock(_MOMENT))
    guard = HubGuard(audit)
    uploader = RecordingUploader()

    guard.run(requested=True, confirmation=_confirmation(), uploader=uploader)
    guard.run(requested=True, confirmation=_confirmation(), uploader=uploader)

    assert uploader.count == 2
    assert len(audit.entries()) == 2
