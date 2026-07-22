"""CTR-PLUG@v1 freeze re-confirmation on the hardware axis (01 §6.2, 06 §4.3).

Per 01 §6.2 CTR-PLUG@v1 is owned and frozen by WP-0A-02 at the Wave 0-A exit —
Wave 0-C consumes it (`0C-01`/`0C-05`/`0C-09`), so freezing it in Wave 1 would make
that earlier consumption a CR-2 violation. WP-1-01 therefore does NOT freeze it; it
re-confirms, on the hardware axis, that the contract is registered in the freeze
authority and reports its lock state. Arming the lock (a FROZEN generation whose
content hash CI-09 verifies) is WP-0A-02's deliverable, and requires WP-0A-02 to
declare a CONTRACT_FROZEN glob over the frozen plugin spec — this module reads the
authority, it never writes it.

Light lane: reads only the committed JSON authority, no LeRobot import.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

CONTRACT_ID = "CTR-PLUG@v1"

# Per 01 §6.2 the owning work package of CTR-PLUG@v1 is WP-0A-02; the freeze
# authority derives owner_wp from that table, so a re-confirmation asserts it.
OWNER_WP = "WP-0A-02"

# The committed freeze authority (`WP-BOOT-05`): the derived index whose
# `contracts[]` carries each generation's status and locked `canonical_hash`.
AUTHORITY = "registry/contracts/contract_index.json"

STATUS_FROZEN = "FROZEN"


@dataclass(frozen=True)
class Registration:
    """CTR-PLUG@v1's record in the freeze authority.

    Attributes:
        present: Whether a CTR-PLUG@v1 record exists in the authority at all.
        status: The generation status (`DRAFT`/`FROZEN`/...), or empty when absent.
        owner_wp: The owning work package the authority records, or empty.
        canonical_hash: The locked content hash for a FROZEN generation, or None.
    """

    present: bool
    status: str
    owner_wp: str
    canonical_hash: str | None


def registration(repo_root: Path) -> Registration:
    """Read CTR-PLUG@v1's registration from the committed freeze authority.

    Args:
        repo_root: Repository root the authority lives under.

    Returns:
        (Registration) The contract's presence, status, owner and locked hash.
    """
    path = repo_root / AUTHORITY
    if not path.is_file():
        return Registration(present=False, status="", owner_wp="", canonical_hash=None)
    index = json.loads(path.read_text(encoding="utf-8"))
    for record in index.get("contracts", []) or []:
        if record.get("contract_id") == CONTRACT_ID:
            return Registration(
                present=True,
                status=str(record.get("status", "")),
                owner_wp=str(record.get("owner_wp", "")),
                canonical_hash=record.get("canonical_hash"),
            )
    return Registration(present=False, status="", owner_wp="", canonical_hash=None)


def is_registered(repo_root: Path) -> bool:
    """Report whether CTR-PLUG@v1 is registered in the freeze authority.

    Args:
        repo_root: Repository root.

    Returns:
        (bool) True when a CTR-PLUG@v1 record is present.
    """
    return registration(repo_root).present


def is_frozen(repo_root: Path) -> bool:
    """Report whether CTR-PLUG@v1 is currently locked (FROZEN with a hash).

    Args:
        repo_root: Repository root.

    Returns:
        (bool) True when the generation is FROZEN and carries a canonical hash.
    """
    state = registration(repo_root)
    return state.status == STATUS_FROZEN and bool(state.canonical_hash)
