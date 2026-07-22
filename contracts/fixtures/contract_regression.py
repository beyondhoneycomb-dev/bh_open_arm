"""The contract regression checker: six frozen hashes, and staleness that propagates.

`02b` §5.2 WP-3A-06 ②: this is the check that fails CI when any of the six frozen
3A contracts (`CTR-PRIM`/`CAM`/`CAP`/`TEL`/`WS`/`REC`@v1) drifts from the hash it
was frozen at, and — the load-bearing half — when `CTR-PRIM@v1` moves, it marks all
five consuming contracts STALE even if their own bytes did not move. A primitive
change invalidates every contract built on it, which is exactly the `CR-2` rule the
freeze machinery encodes and 3B would otherwise amplify thirteen ways.

Two anti-forge properties hold by construction:

- The locked value is read from the committed freeze authority
  (`registry/contracts/contract_index.json`), never recomputed. A checker that
  re-hashed the current files and compared them to themselves would always pass.
- The current value is computed by the one CI-09 hashing primitive
  (`ci_09.content_hash`), so the number this checker compares is the same number
  the freeze locked and CI-09 later re-checks — they cannot drift apart.

The dependency edge — which contracts consume `CTR-PRIM@v1` — is derived from the
registry's `consumes` axis, not hard-coded, so a sixth consumer added later is
caught by the same propagation without editing this file.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from registry.checks.ci_09 import frozen_content_hash
from registry.checks.corpus import Corpus

# The primitive whose change makes every consumer stale (`02b` §5.0b).
SHARED_PRIMITIVE_CONTRACT = "CTR-PRIM@v1"

# The committed freeze authority: the single source of the locked hashes, recorded
# by a FREEZE event and never recomputed by a generator (`06` §4.2, CI-09).
AUTHORITY_RELPATH = "registry/contracts/contract_index.json"

_STATUS_FROZEN = "FROZEN"


@dataclass(frozen=True)
class RegressionReport:
    """The verdict of one regression run over the six frozen contracts.

    Attributes:
        ok: True only when no tracked contract's content drifted from its lock.
        checked: The contract ids the run compared, in a stable order.
        mismatches: Contracts whose on-disk content hash no longer equals the lock.
        stale: Consuming contracts invalidated because `CTR-PRIM@v1` changed —
            flagged regardless of whether their own bytes moved.
        actual: The recomputed content hash per contract (None when absent).
        locked: The registered hash per contract from the authority (None when absent).
    """

    ok: bool
    checked: tuple[str, ...]
    mismatches: tuple[str, ...]
    stale: tuple[str, ...]
    actual: Mapping[str, str | None]
    locked: Mapping[str, str | None]

    def summary(self) -> str:
        """Render a one-line human summary of the run.

        Returns:
            (str) A PASS/FAIL line naming the mismatched and stale contracts.
        """
        if self.ok:
            return f"contract regression PASS — {len(self.checked)} frozen contracts match locks"
        parts = [f"contract regression FAIL over {len(self.checked)} contracts"]
        if self.mismatches:
            parts.append(f"drifted: {', '.join(self.mismatches)}")
        if self.stale:
            parts.append(f"stale (CTR-PRIM@v1 changed): {', '.join(self.stale)}")
        return "; ".join(parts)


def prim_consumer_contracts(corpus: Corpus) -> tuple[str, ...]:
    """Return the contracts whose producing work package consumes `CTR-PRIM@v1`.

    Derived from the registry `consumes`/`produces` axes rather than named here, so
    the consumer set is whatever the frozen registry says it is.

    Args:
        corpus: The corpus to read the registry axes from.

    Returns:
        (tuple[str, ...]) The consuming contract ids, sorted and unique.
    """
    consumers: set[str] = set()
    for entry in corpus.work_entries:
        contract = entry.get("contract") or {}
        if SHARED_PRIMITIVE_CONTRACT in (contract.get("consumes") or []):
            consumers.update(str(produced) for produced in (contract.get("produces") or []))
    return tuple(sorted(consumers))


def tracked_contract_ids(corpus: Corpus) -> tuple[str, ...]:
    """Return the six contracts this checker guards: the primitive and its consumers.

    Args:
        corpus: The corpus to derive the consumer set from.

    Returns:
        (tuple[str, ...]) `CTR-PRIM@v1` first, then its consumer contracts sorted.
    """
    return (SHARED_PRIMITIVE_CONTRACT, *prim_consumer_contracts(corpus))


def load_locked_hashes(authority_path: Path) -> dict[str, str]:
    """Read the locked `canonical_hash` of every FROZEN generation from the authority.

    Args:
        authority_path: Path to the committed `contract_index.json`.

    Returns:
        (dict[str, str]) Contract id to its locked hash, for FROZEN generations only.
    """
    if not authority_path.is_file():
        return {}
    document = json.loads(authority_path.read_text(encoding="utf-8"))
    locked: dict[str, str] = {}
    for record in document.get("contracts", []) or []:
        if record.get("status") != _STATUS_FROZEN:
            continue
        contract_id = record.get("contract_id")
        canonical_hash = record.get("canonical_hash")
        if isinstance(contract_id, str) and isinstance(canonical_hash, str) and canonical_hash:
            locked[contract_id] = canonical_hash
    return locked


def check_contract_regression(corpus: Corpus, authority_path: Path) -> RegressionReport:
    """Compare each frozen 3A contract's on-disk content against its committed lock.

    Args:
        corpus: The corpus holding the registry and the file tree to hash.
        authority_path: Path to the committed freeze authority.

    Returns:
        (RegressionReport) The mismatches and the CTR-PRIM-driven stale set.
    """
    checked = tracked_contract_ids(corpus)
    locked = load_locked_hashes(authority_path)
    actual: dict[str, str | None] = {
        contract_id: frozen_content_hash(corpus, contract_id) for contract_id in checked
    }
    mismatches = tuple(
        contract_id for contract_id in checked if locked.get(contract_id) != actual[contract_id]
    )
    prim_changed = SHARED_PRIMITIVE_CONTRACT in mismatches
    stale = prim_consumer_contracts(corpus) if prim_changed else ()
    return RegressionReport(
        ok=not mismatches,
        checked=checked,
        mismatches=mismatches,
        stale=stale,
        actual=actual,
        locked={contract_id: locked.get(contract_id) for contract_id in checked},
    )


def check_repo(root: Path) -> RegressionReport:
    """Run the regression check against a repository checkout.

    Args:
        root: Repository root holding the registry, the authority and the contracts.

    Returns:
        (RegressionReport) The verdict for the committed tree.
    """
    return check_contract_regression(Corpus(root), root / AUTHORITY_RELPATH)


def main() -> int:
    """Run the regression check over the current repository and report an exit code.

    Returns:
        (int) 0 when every frozen contract matches its lock, 1 on any drift.
    """
    report = check_repo(Path.cwd())
    print(report.summary())
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
