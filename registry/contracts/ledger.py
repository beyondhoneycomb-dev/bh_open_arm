"""Append-only, digest-chained log of freeze events.

`contract_index.json` is a derived document, never a source. If it were the
place freeze state lived, then editing it by hand would *be* the freeze, and
`06` §4.2 would have a lock whose key is a text editor. State lives here
instead, as events, and the index is recomputed from them.

Every event carries a digest over its own fields and its predecessor's digest.
This does not authenticate a writer — anyone able to edit the file can also
recompute the chain. What it buys is that tampering cannot be *local*: altering
one historical freeze invalidates every digest after it, so a silent one-line
edit becomes a whole-file rewrite that git records. Integrity ultimately rests
on the reviewed history of this file, and the chain is what makes a breach
visible there rather than plausible.

State is a fold over events, never a mutation of a row, because a freeze that
can be overwritten in place is not a freeze.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import yaml

from registry.contracts.violations import SEVERITY_BLOCKING, Violation

LEDGER_VERSION = 1
GENESIS_DIGEST = "0" * 64

FREEZE = "FREEZE"
SUPERSEDE = "SUPERSEDE"
RETIRE = "RETIRE"
EVENT_KINDS = frozenset({FREEZE, SUPERSEDE, RETIRE})


@dataclass(frozen=True)
class LedgerEvent:
    """One recorded transition of a contract's freeze state.

    Attributes:
        seq: 1-based position in the chain.
        kind: One of `EVENT_KINDS`.
        contract_id: Contract the event applies to, in `CTR-<NAME>@v<n>` form.
        canonical_hash: Content hash locked by a `FREEZE`; `None` otherwise,
            since a supersede or retire changes status without touching bytes.
        prev_digest: Digest of the preceding event, or `GENESIS_DIGEST`.
        digest: Digest of this event, binding its fields to `prev_digest`.
    """

    seq: int
    kind: str
    contract_id: str
    canonical_hash: str | None
    prev_digest: str
    digest: str


def event_digest(
    seq: int, kind: str, contract_id: str, canonical_hash: str | None, prev_digest: str
) -> str:
    """Compute the digest binding one event to its predecessor.

    Args:
        seq: 1-based position in the chain.
        kind: Event kind.
        contract_id: Contract the event applies to.
        canonical_hash: Locked content hash, or `None`.
        prev_digest: Digest of the preceding event.

    Returns:
        str: Hex digest over the event fields and the predecessor digest.
    """
    payload = json.dumps(
        {
            "seq": seq,
            "kind": kind,
            "contract_id": contract_id,
            "canonical_hash": canonical_hash,
            "prev_digest": prev_digest,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def read_ledger(path: Path) -> list[LedgerEvent]:
    """Load the event log.

    Args:
        path: Ledger file path.

    Returns:
        list[LedgerEvent]: Events in recorded order; empty when no ledger
            exists yet, which is the lawful state before the first freeze.
    """
    if not path.exists():
        return []
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [
        LedgerEvent(
            seq=int(row["seq"]),
            kind=str(row["kind"]),
            contract_id=str(row["contract_id"]),
            canonical_hash=row["canonical_hash"],
            prev_digest=str(row["prev_digest"]),
            digest=str(row["digest"]),
        )
        for row in document.get("events", [])
    ]


def verify_chain(events: list[LedgerEvent]) -> list[Violation]:
    """Check that every event's digest binds it to the recorded history.

    Args:
        events: Events in recorded order.

    Returns:
        list[Violation]: One entry per event whose sequence, linkage or digest
            does not reconstruct. Empty when the chain is intact.
    """
    violations: list[Violation] = []
    prev_digest = GENESIS_DIGEST
    for offset, event in enumerate(events):
        expected_seq = offset + 1
        location = f"{event.contract_id} (ledger seq {event.seq})"
        if event.seq != expected_seq:
            violations.append(
                Violation(
                    rule="CI-09",
                    severity=SEVERITY_BLOCKING,
                    location=location,
                    expected=f"seq {expected_seq}",
                    actual=f"seq {event.seq}",
                )
            )
        if event.kind not in EVENT_KINDS:
            violations.append(
                Violation(
                    rule="CI-09",
                    severity=SEVERITY_BLOCKING,
                    location=location,
                    expected=f"kind in {sorted(EVENT_KINDS)}",
                    actual=event.kind,
                )
            )
        if event.prev_digest != prev_digest:
            violations.append(
                Violation(
                    rule="CI-09",
                    severity=SEVERITY_BLOCKING,
                    location=location,
                    expected=f"prev_digest {prev_digest}",
                    actual=event.prev_digest,
                )
            )
        recomputed = event_digest(
            event.seq, event.kind, event.contract_id, event.canonical_hash, event.prev_digest
        )
        if recomputed != event.digest:
            violations.append(
                Violation(
                    rule="CI-09",
                    severity=SEVERITY_BLOCKING,
                    location=location,
                    expected=f"digest {recomputed}",
                    actual=f"{event.digest} (ledger entry was edited in place)",
                )
            )
        prev_digest = event.digest
    return violations


def head_digest(events: list[LedgerEvent]) -> str:
    """Return the digest the next appended event must chain onto.

    Args:
        events: Events in recorded order.

    Returns:
        str: Digest of the last event, or `GENESIS_DIGEST` when empty.
    """
    return events[-1].digest if events else GENESIS_DIGEST


def append_events(
    path: Path, events: list[LedgerEvent], pending: list[tuple[str, str, str | None]]
) -> list[LedgerEvent]:
    """Append events to the ledger and rewrite it atomically.

    Args:
        path: Ledger file path.
        events: Events already recorded, in order.
        pending: New events as `(kind, contract_id, canonical_hash)` tuples,
            applied in the order given.

    Returns:
        list[LedgerEvent]: The full event list after appending.
    """
    appended = list(events)
    for kind, contract_id, content_hash in pending:
        seq = len(appended) + 1
        prev = head_digest(appended)
        appended.append(
            LedgerEvent(
                seq=seq,
                kind=kind,
                contract_id=contract_id,
                canonical_hash=content_hash,
                prev_digest=prev,
                digest=event_digest(seq, kind, contract_id, content_hash, prev),
            )
        )
    document = {
        "version": LEDGER_VERSION,
        "events": [
            {
                "seq": event.seq,
                "kind": event.kind,
                "contract_id": event.contract_id,
                "canonical_hash": event.canonical_hash,
                "prev_digest": event.prev_digest,
                "digest": event.digest,
            }
            for event in appended
        ],
    }
    write_atomic(path, yaml.safe_dump(document, sort_keys=False, allow_unicode=True))
    return appended


def write_atomic(path: Path, text: str) -> None:
    """Replace a file's contents without leaving a truncated intermediate.

    The store's write primitive, shared with the index writer. A crash between
    truncate and write would leave a ledger that verifies as tampered rather
    than as absent, and that is the one failure mode this package cannot
    distinguish from an attack.

    Args:
        path: Destination path.
        text: Full file contents.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    scratch = path.with_suffix(f"{path.suffix}.tmp")
    scratch.write_text(text, encoding="utf-8")
    scratch.replace(path)
