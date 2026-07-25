"""CG-5-08i — push_to_hub demands explicit confirm + audit (FR-OPS-082).

An upload is legal only with an explicit per-upload confirmation, and the audit entry
is written before the upload runs. An unspecified `push_to_hub` resolves to False (the
upstream True is overridden). This exercises the reused `ops.hubguard` gate through the
WP-5-08 upload surface.
"""

from __future__ import annotations

from pathlib import Path

from backend.security.hub_upload import (
    DatasetUploadSecurity,
    UploadConfirmation,
    UploadTarget,
)

_TARGET = UploadTarget(repo_id="openarm/demo", private=True, account="openarm-lab")
_DATASET = "openarm/demo"
_WHO = "operator-1"


class RecordingUploader:
    """A test uploader that records each call instead of pushing to a live Hub."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, UploadTarget]] = []

    def __call__(self, dataset: str, target: UploadTarget) -> None:
        self.calls.append((dataset, target))


def test_upload_requested_without_confirmation_is_suppressed(tmp_path: Path) -> None:
    audit_path = tmp_path / "uploads.jsonl"
    security = DatasetUploadSecurity(audit_path)
    uploader = RecordingUploader()

    decision = security.request_upload(requested=True, confirmation=None, uploader=uploader)

    assert decision.push_to_hub is False
    assert decision.suppressed is True
    assert uploader.calls == []
    assert not audit_path.exists()


def test_confirmed_upload_runs_once_and_is_audited(tmp_path: Path) -> None:
    audit_path = tmp_path / "uploads.jsonl"
    security = DatasetUploadSecurity(audit_path)
    uploader = RecordingUploader()
    confirmation = UploadConfirmation(who=_WHO, dataset=_DATASET, target=_TARGET)

    decision = security.request_upload(requested=True, confirmation=confirmation, uploader=uploader)

    assert decision.push_to_hub is True
    assert uploader.calls == [(_DATASET, _TARGET)]
    audit_lines = audit_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(audit_lines) == 1
    assert _WHO in audit_lines[0]


def test_unspecified_push_to_hub_defaults_to_local(tmp_path: Path) -> None:
    security = DatasetUploadSecurity(tmp_path / "uploads.jsonl")
    uploader = RecordingUploader()

    decision = security.request_upload(requested=None, confirmation=None, uploader=uploader)

    assert decision.push_to_hub is False
    assert uploader.calls == []
