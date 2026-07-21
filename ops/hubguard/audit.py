"""Append-only audit trail for confirmed dataset uploads.

FR-OPS-082 and spec 14 F25 make an upload legal only after two steps: an explicit
user confirmation and an audit-log entry. This module owns the second step. An
upload authorised with no matching audit line is exactly the unaudited-upload
incident the policy forbids, so the guard writes the entry BEFORE the network call
(see `push_policy.HubGuard`): the record of intent then survives a failed, killed,
or crashed upload.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class UploadTarget:
    """Where a confirmed upload is destined.

    Attributes:
        repo_id: Hugging Face Hub dataset repo id.
        private: Whether the destination Hub repo is private.
        account: Hub account/namespace the push authenticates as.
    """

    repo_id: str
    private: bool
    account: str

    def describe(self) -> str:
        """Return a one-line human description of the destination."""
        visibility = "private" if self.private else "public"
        return f"{self.account}/{self.repo_id} ({visibility})"


@dataclass(frozen=True)
class AuditEntry:
    """One recorded upload authorisation — the {who, when, dataset, target} tuple.

    `when` is an ISO-8601 UTC string so the serialised log is timezone-explicit and
    stable across readers rather than dependent on the reader's locale.
    """

    who: str
    when: str
    dataset: str
    target: UploadTarget

    def to_json(self) -> dict[str, Any]:
        """Serialise to the JSON object one audit line holds."""
        return {
            "who": self.who,
            "when": self.when,
            "dataset": self.dataset,
            "target": {
                "repo_id": self.target.repo_id,
                "private": self.target.private,
                "account": self.target.account,
            },
        }


def _utc_now() -> datetime:
    """Return the current instant in UTC. Injectable so tests are deterministic."""
    return datetime.now(UTC)


class UploadAuditLog:
    """Append-only JSONL audit log of confirmed uploads.

    Ownership: the guard that authorises an upload holds the sole instance and is
    the only writer; readers reopen the file. Append-only is the point — an audit
    trail that can be rewritten in place is not evidence.
    """

    def __init__(self, path: Path, clock: Callable[[], datetime] = _utc_now) -> None:
        self._path = path
        self._clock = clock

    def record(self, who: str, dataset: str, target: UploadTarget) -> AuditEntry:
        """Append one entry stamped with the current time and return it.

        Args:
            who: Identity that confirmed the upload.
            dataset: Dataset repo id being uploaded.
            target: Destination of the upload.

        Returns:
            (AuditEntry) The entry just appended.
        """
        entry = AuditEntry(
            who=who,
            when=self._clock().isoformat(),
            dataset=dataset,
            target=target,
        )
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry.to_json(), ensure_ascii=False) + "\n")
        return entry

    def entries(self) -> list[AuditEntry]:
        """Read the log back into entries, oldest first.

        Returns:
            (list[AuditEntry]) Every recorded entry, or empty when no log exists.
        """
        if not self._path.exists():
            return []
        out: list[AuditEntry] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            raw = json.loads(stripped)
            target = raw["target"]
            out.append(
                AuditEntry(
                    who=raw["who"],
                    when=raw["when"],
                    dataset=raw["dataset"],
                    target=UploadTarget(
                        repo_id=target["repo_id"],
                        private=target["private"],
                        account=target["account"],
                    ),
                )
            )
        return out
