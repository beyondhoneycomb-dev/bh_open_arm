"""CI-09 — freeze violation: a frozen contract's content hash must never move.

`06` §4.3 was corrected on this point and the correction is the rule: there is no
exception, and adding an optional field is a mismatch like any other. Two schemas
sharing one `@v<n>` destroys the answer to "what did I implement against", so
widening a contract means `@v(n+1)`. Re-hashing an existing `@v<n>` is not legal
for any reason — `CR-2` outranks the older optional-field carve-out.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from registry.checks.corpus import Corpus
from registry.checks.globs import expand, split_globs
from registry.checks.model import RuleResult, fail

RULE_ID = "CI-09"
TITLE = "freeze violation"

MODE_CONTRACT_FROZEN = "CONTRACT_FROZEN"
CONTRACT_INDEX = "registry/build/contract_index.json"


def content_hash(paths: tuple[str, ...], root: Path) -> str:
    """Hash the content of a frozen contract's files.

    Files are hashed in sorted path order with the path folded in, so that moving a
    definition between two files of a frozen contract is a mismatch rather than a
    coincidence of equal bytes.

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


def _load_index(corpus: Corpus) -> dict[str, Any]:
    """Read the contract index if `WP-BOOT-05` has registered one.

    Args:
        corpus: The corpus under test.

    Returns:
        (dict[str, Any]) Contract id to registered record, empty when absent.
    """
    path = corpus.root / CONTRACT_INDEX
    if not path.is_file():
        return {}
    loaded: Any = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(loaded, dict):
        contracts = loaded.get("contracts", loaded)
        if isinstance(contracts, dict):
            return contracts
    return {}


def run(corpus: Corpus) -> RuleResult:
    """Report frozen contracts whose file content no longer matches the index.

    Args:
        corpus: The corpus under test.

    Returns:
        (RuleResult) One finding per hash mismatch or unregistered frozen contract.
    """
    index = _load_index(corpus)

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

    findings = []
    hashed = 0
    for contract_id, globs in sorted(frozen.items()):
        files = expand(tuple(sorted(globs)), corpus.tracked_files)
        if not files:
            continue
        hashed += 1
        actual = content_hash(tuple(files), corpus.root)
        registered = index.get(contract_id)
        expected = str(registered.get("hash", "")) if isinstance(registered, dict) else ""
        if not expected:
            findings.append(
                fail(
                    rule_id=RULE_ID,
                    req_or_wp=contract_id,
                    path=CONTRACT_INDEX,
                    reason=(
                        "frozen contract has content on disk but no registered hash, so the "
                        "freeze is a declaration rather than a lock"
                    ),
                    expected=f"a hash entry for {contract_id} in the contract index",
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
    elif not index:
        notes = (
            f"{CONTRACT_INDEX} does not exist yet (WP-BOOT-05 has not registered contracts), "
            "so no freeze can be verified against it.",
        )

    return RuleResult(
        rule_id=RULE_ID,
        findings=tuple(findings),
        sites=hashed,
        vacuous=not hashed,
        notes=notes,
    )
