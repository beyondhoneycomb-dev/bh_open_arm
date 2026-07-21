"""Contract-version freeze guard for CTR-ACT@v1 (acceptance ⑧).

A frozen contract may not change silently: any change to the schema is a new
generation and must bump the version, never re-hash the same one (06 §4.3, §4.2 —
even adding an optional field is a mismatch). The real freeze registry (CI-09,
WP-BOOT-05) is not standing yet, so this module supplies the check locally: the
frozen file pins the digest of its own content, and a change that does not bump
the version leaves that digest stale.

`schema_digest` hashes the whole contract document with only the `frozen_digest`
field removed, so the digest cannot certify itself and every other change — a new
channel, a changed unit, an added field — moves it. That is the strict sense the
freeze needs (06 §4.3): the digest is sensitive to any content change at all.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

FROZEN_DIGEST_FIELD = "frozen_digest"
CONTRACT_FIELD = "contract"

HASH_PREFIX = "sha256:"

REASON_STALE_DIGEST = "frozen_digest does not match the schema content"
REASON_NO_BUMP = "schema content changed but the contract version was not bumped"


@dataclass(frozen=True)
class VersionVerdict:
    """The outcome of comparing a schema revision against its frozen predecessor.

    Attributes:
        accepted: True when the change is either a no-op or a proper version bump.
        reason: Why it was rejected, empty when accepted.
        previous_version: The prior contract id, e.g. `CTR-ACT@v1`.
        current_version: The revised contract id.
    """

    accepted: bool
    reason: str
    previous_version: str
    current_version: str


def schema_digest(document: dict[str, Any]) -> str:
    """Compute the content digest of a contract document.

    Every field except `frozen_digest` is included, so the digest is sensitive to
    any schema change and cannot certify itself.

    Args:
        document: The parsed contract mapping.

    Returns:
        (str) `sha256:<hex>` over the canonical JSON of the document minus its
        own digest field.
    """
    core = {key: value for key, value in document.items() if key != FROZEN_DIGEST_FIELD}
    blob = json.dumps(core, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"{HASH_PREFIX}{hashlib.sha256(blob.encode('utf-8')).hexdigest()}"


def verify_frozen_digest(document: dict[str, Any]) -> tuple[str, ...]:
    """Check a contract document's pinned digest matches its content.

    Args:
        document: The parsed contract mapping.

    Returns:
        (tuple[str, ...]) A single message when the pinned digest is stale; empty
        when it matches.
    """
    pinned = str(document.get(FROZEN_DIGEST_FIELD, ""))
    actual = schema_digest(document)
    if pinned != actual:
        return (f"{REASON_STALE_DIGEST}: pinned {pinned}, actual {actual}",)
    return ()


def check_version_bump(previous: dict[str, Any], current: dict[str, Any]) -> VersionVerdict:
    """Decide whether a schema revision is a legal change.

    A revision is legal only if the content is unchanged, or the content changed
    AND the contract version was bumped. A changed schema keeping the same version
    is the silent-drift case CI rejects (acceptance ⑧).

    Args:
        previous: The frozen predecessor document.
        current: The revised document.

    Returns:
        (VersionVerdict) Accepted for a no-op or a proper bump; rejected for a
        changed schema that kept its version.
    """
    previous_version = str(previous.get(CONTRACT_FIELD, ""))
    current_version = str(current.get(CONTRACT_FIELD, ""))
    changed = schema_digest(previous) != schema_digest(current)
    if changed and previous_version == current_version:
        return VersionVerdict(False, REASON_NO_BUMP, previous_version, current_version)
    return VersionVerdict(True, "", previous_version, current_version)
