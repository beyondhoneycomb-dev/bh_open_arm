"""Seeder hook: which registry records must carry the normalization hash.

`CI-07` fires on a contested record whose `normalization` slot is null. A record
is settled by the ledger when its requirement is a winning id or the requirement
of a discarded reading, so the seeder stamps exactly those records with the
issued hash and leaves every other contested record null — where `CI-07` should
still fire.

The hash is the WP-N1-04 issuance: the canonical serialization of the ledger
joined to the WP-N1-03 gate mapping (`registry/normalization/hash.py`). The set
of stamped records is derived from the ledger's *structured* winners and discarded
requirements, never from a free-text scan of the same columns `CI-07` reads;
stamping every column mention would make `CI-07`'s ledger branch green while
catching nothing, the outcome `02a` §-2.3 names the worst.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from registry.normalization.content_hash import HASH_PREFIX as HASH_PREFIX
from registry.normalization.content_hash import issue
from registry.normalization.loader import load_ledger

LEDGER_RELPATH = Path("normalization") / "ledger.yaml"
GATE_MAP_RELPATH = Path("normalization") / "gate_spec_map.yaml"


@dataclass(frozen=True)
class LedgerSeed:
    """The records the ledger settles, and the hash they must carry.

    Attributes:
        settled_ids: Requirement ids the ledger resolves — winners and the
            requirements of discarded readings.
        digest: The issued normalization hash, or None when no ledger exists.
    """

    settled_ids: frozenset[str]
    digest: str | None

    def normalization_for(self, req: str) -> str | None:
        """Return the hash a record's requirement must carry, if any.

        Args:
            req: A registry record's requirement id.

        Returns:
            (str | None) The ledger hash when the requirement is settled, else None.
        """
        return self.digest if req in self.settled_ids else None


def ledger_seed(plan_dir: Path) -> LedgerSeed:
    """Read the ledger and derive the seeder's normalization inputs.

    A missing ledger is the expected pre-`WP-N1-02` state, not an error: the
    seeder must run at bootstrap when no ledger exists yet, so this returns an
    empty seed and the seeder stamps nothing.

    Args:
        plan_dir: Directory holding the planning documents.

    Returns:
        (LedgerSeed) Settled ids and the issued hash, or an empty seed.
    """
    path = plan_dir / LEDGER_RELPATH
    if not path.is_file():
        return LedgerSeed(settled_ids=frozenset(), digest=None)

    document = load_ledger(path)
    settled: set[str] = set()
    for row in document.get("rows", []):
        settled.update(str(winner) for winner in row.get("winners", []))
        for item in row.get("discarded", []):
            req = item.get("req")
            if req:
                settled.add(str(req))

    digest = issue(path, plan_dir / GATE_MAP_RELPATH)
    return LedgerSeed(settled_ids=frozenset(settled), digest=digest)
