"""CI-09 — freeze violation: a frozen contract's content hash must never move.

`06` §4.3 was corrected on this point and the correction is the rule: there is no
exception, and adding an optional field is a mismatch like any other. Two schemas
sharing one `@v<n>` destroys the answer to "what did I implement against", so
widening a contract means `@v(n+1)`. Re-hashing an existing `@v<n>` is not legal
for any reason — `CR-2` outranks the older optional-field carve-out.

The registered hash is read from the freeze authority — the committed
`registry/contracts/contract_index.json` (`WP-BOOT-05`), whose `contracts[]`
carries `canonical_hash` for every `FROZEN` generation. That value is recorded
once, by a `FREEZE` event in the append-only ledger, and never recomputed by a
generator; this check compares it to the *current* content hash of the frozen
glob, so any byte change is a mismatch. Reading a hash a generator recomputes
each run would be a forge — the frozen value must live in a source, or the lock
is indistinguishable from "hash whatever is on disk".
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from registry.checks.corpus import Corpus
from registry.checks.globs import expand, split_globs
from registry.checks.model import RuleResult, fail

RULE_ID = "CI-09"
TITLE = "freeze violation"

MODE_CONTRACT_FROZEN = "CONTRACT_FROZEN"

# The freeze authority (`WP-BOOT-05`): a committed source whose `contracts[]`
# holds the `canonical_hash` a `FREEZE` event locked. `registry/build/` is the
# BOOT-02 build index — producers/consumers only, no hash — so reading it here
# would find no registered hash and fire on every frozen glob.
CONTRACT_INDEX = "registry/contracts/contract_index.json"

# The one `contracts[].status` value that carries a locked hash. A `DRAFT`,
# `SUPERSEDED` or `RETIRED` generation is not a live freeze, so its hash (if any)
# is not the value a frozen glob must match.
STATUS_FROZEN = "FROZEN"


def content_hash(paths: tuple[str, ...], root: Path) -> str:
    """Hash the content of a frozen contract's files.

    Files are hashed in sorted path order with the path folded in, so that moving a
    definition between two files of a frozen contract is a mismatch rather than a
    coincidence of equal bytes.

    This is the single hashing primitive: the freeze path that records a glob
    contract's `canonical_hash` computes it through here as well, so the frozen
    value and the value this check compares against can never diverge.

    Args:
        paths: Root-relative file paths covered by the frozen glob.
        root: Repository root.

    Returns:
        (str) `sha256:<hex>` over the frozen file set.
    """
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update((root / path).read_bytes())
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def frozen_globs(corpus: Corpus) -> dict[str, set[str]]:
    """Map each contract id to the CONTRACT_FROZEN globs declared for it.

    A `CONTRACT_FROZEN` `owns[]` glob on a record that produces a contract freezes
    that contract's file content. Phase-scoped `owns[]` count too, so a contract
    frozen only inside one phase is still seen.

    Args:
        corpus: The corpus under test.

    Returns:
        (dict[str, set[str]]) Contract id to its declared frozen globs.
    """
    frozen: dict[str, set[str]] = {}
    for record in corpus.entries:
        produces = (record.get("contract", {}) or {}).get("produces", []) or []
        owned = list(record.get("owns", []) or [])
        for phase in record.get("phases", []) or []:
            owned.extend(phase.get("owns", []) or [])
        for entry in owned:
            if entry.get("mode") != MODE_CONTRACT_FROZEN:
                continue
            for contract_id in produces:
                frozen.setdefault(str(contract_id), set()).update(
                    split_globs(str(entry.get("glob", "")))
                )
    return frozen


def frozen_content_hash(corpus: Corpus, contract_id: str) -> str | None:
    """Content hash of one frozen contract's on-disk glob files.

    The freeze path calls this to record a glob contract's `canonical_hash`; it
    expands the same globs against the same tracked-file set this check uses, so
    the frozen value is exactly what a later `run` recomputes.

    Args:
        corpus: The corpus the contract is declared in.
        contract_id: Contract id whose frozen glob to hash.

    Returns:
        (str | None) `sha256:<hex>` over the frozen files, or None when the
            contract declares no frozen glob or none of its files exist yet.
    """
    globs = frozen_globs(corpus).get(contract_id)
    if not globs:
        return None
    files = expand(tuple(sorted(globs)), corpus.tracked_files)
    if not files:
        return None
    return content_hash(tuple(files), corpus.root)


def _load_frozen_hashes(corpus: Corpus) -> dict[str, str]:
    """Read the frozen `canonical_hash` of every FROZEN generation.

    Reads the freeze authority, not the BOOT-02 build index: only a `FROZEN`
    generation with a recorded hash is a lock this check can verify against.

    Args:
        corpus: The corpus under test.

    Returns:
        (dict[str, str]) Contract id to its locked `canonical_hash`, for FROZEN
            generations only; empty when the authority is absent.
    """
    path = corpus.root / CONTRACT_INDEX
    if not path.is_file():
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        return {}
    frozen: dict[str, str] = {}
    for record in loaded.get("contracts", []) or []:
        if not isinstance(record, dict):
            continue
        if record.get("status") != STATUS_FROZEN:
            continue
        contract_id = record.get("contract_id")
        canonical_hash = record.get("canonical_hash")
        if isinstance(contract_id, str) and isinstance(canonical_hash, str) and canonical_hash:
            frozen[contract_id] = canonical_hash
    return frozen


def run(corpus: Corpus) -> RuleResult:
    """Report frozen contracts whose file content no longer matches the authority.

    Args:
        corpus: The corpus under test.

    Returns:
        (RuleResult) One finding per hash mismatch or unregistered frozen contract.
    """
    registered = _load_frozen_hashes(corpus)
    frozen = frozen_globs(corpus)

    findings = []
    hashed = 0
    for contract_id, globs in sorted(frozen.items()):
        files = expand(tuple(sorted(globs)), corpus.tracked_files)
        if not files:
            continue
        hashed += 1
        actual = content_hash(tuple(files), corpus.root)
        expected = registered.get(contract_id, "")
        if not expected:
            findings.append(
                fail(
                    rule_id=RULE_ID,
                    req_or_wp=contract_id,
                    path=CONTRACT_INDEX,
                    reason=(
                        "frozen contract has content on disk but no FROZEN hash in the freeze "
                        "authority, so the freeze is a declaration rather than a lock"
                    ),
                    expected=f"a FROZEN {contract_id} with a canonical_hash in the authority",
                    actual=f"absent; on-disk content hashes to {actual}",
                )
            )
            continue
        if expected != actual:
            findings.append(
                fail(
                    rule_id=RULE_ID,
                    req_or_wp=contract_id,
                    path=", ".join(sorted(files)[:4]),
                    reason=(
                        "frozen contract content differs from its registered hash; widening a "
                        "contract requires @v(n+1), and no field addition is exempt"
                    ),
                    expected=expected,
                    actual=actual,
                )
            )

    notes: tuple[str, ...] = ()
    if not hashed:
        notes = (
            f"{len(frozen)} frozen contract(s) are declared but none has content on disk, "
            "so no freeze was verified; detection is proven by fixture, not by this run.",
        )
    elif not registered:
        notes = (
            f"{CONTRACT_INDEX} registers no FROZEN generation (WP-BOOT-05 has frozen nothing "
            "yet), so no freeze can be verified against it.",
        )

    return RuleResult(
        rule_id=RULE_ID,
        findings=tuple(findings),
        sites=hashed,
        vacuous=not hashed,
        notes=notes,
    )
