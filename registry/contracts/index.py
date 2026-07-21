"""The contract index and the transitions allowed to change it.

`contract_index.json` is a pure function of three inputs: the canonical
contract table (`01` §6.2), the registry's `consumes` axis
(`registry/traceability.yaml`), and the freeze ledger. It is written by
`write_index` and by nothing else, and `verify_index` recomputes it from those
inputs and rejects any difference. That is what closes the bypass: an edit to
the JSON is not detected by enumerating who may write the file, but by the file
no longer being what its sources say it is, which holds however the edit was
made.

Rule ids on emitted violations map to their canonical definitions:

- `CI-03`   the owning work package disagrees with `01` §6.2.
- `CI-03c`  a contract id outside the closed 13-name namespace.
- `CI-08`   an id that is not `CTR-<NAME>@v<n>`.
- `CI-09`   a frozen generation's content hash changed, or the index does not
            reconstruct from its sources.
- `CR-2`    a work package consumes a contract that is not frozen.
- `CR-3`    a freeze that does not follow the `@v(n+1)` issuing procedure.
- `CR-5`    the index's consumer axis disagrees with the registry's `consumes`
            axis, which `05` §0.1 makes canonical.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from registry.contracts import ledger
from registry.contracts.canonical import canonical_hash
from registry.contracts.catalog import (
    CANONICAL_DOC,
    ContractDefinition,
    ContractRef,
    load_catalog,
    parse_contract_id,
    require_in_namespace,
)
from registry.contracts.violations import SEVERITY_BLOCKING, ContractViolationError, Violation

INDEX_VERSION = 1
NAMESPACE = "CTR-<NAME>@v<n>"

DRAFT = "DRAFT"
FROZEN = "FROZEN"
SUPERSEDED = "SUPERSEDED"
RETIRED = "RETIRED"

# A consumer may keep reading a superseded generation while its named
# replacement work package lands (`06` §4.3 procedure step 3). `RETIRED` is the
# state that closes that window, so only `DRAFT` and `RETIRED` block a start.
CONSUMABLE_STATUSES = frozenset({FROZEN, SUPERSEDED})

_DEFAULT_REGISTRY = Path("registry/traceability.yaml")
_DEFAULT_LEDGER = Path("registry/contracts/freeze_ledger.yaml")
_DEFAULT_INDEX = Path("registry/contracts/contract_index.json")


@dataclass(frozen=True)
class ContractStore:
    """The four locations the contract index is derived from and written to.

    Grouped rather than passed separately because the index is a pure function
    of the first three: an operation taking them individually could be handed a
    ledger from one tree and a registry from another, and would then produce an
    index that verifies against neither while looking entirely well-formed.

    Attributes:
        plan_root: Repository root the planning documents live under.
        registry_path: Path to `registry/traceability.yaml`.
        ledger_path: Path to the append-only freeze ledger.
        index_path: Path to the generated `contract_index.json`.
    """

    plan_root: Path
    registry_path: Path
    ledger_path: Path
    index_path: Path

    @classmethod
    def at(cls, repo_root: Path) -> ContractStore:
        """Build a store rooted at a repository checkout.

        Args:
            repo_root: Repository root.

        Returns:
            ContractStore: Store using the canonical in-repo locations.
        """
        return cls(
            plan_root=repo_root,
            registry_path=repo_root / _DEFAULT_REGISTRY,
            ledger_path=repo_root / _DEFAULT_LEDGER,
            index_path=repo_root / _DEFAULT_INDEX,
        )


@dataclass(frozen=True)
class ContractRecord:
    """One contract generation as the index publishes it.

    Attributes:
        contract_id: Id in `CTR-<NAME>@v<n>` form.
        version: Freeze generation.
        canonical_hash: Locked content hash, or `None` before the freeze.
        status: One of `DRAFT`, `FROZEN`, `SUPERSEDED`, `RETIRED`.
        owner_wp: Owning work package, from `01` §6.2.
        consumer_wps: Work packages declaring this id in `consumes`, derived
            from the registry.
    """

    contract_id: str
    version: int
    canonical_hash: str | None
    status: str
    owner_wp: str
    consumer_wps: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """Return the record in the index's serialized shape.

        Returns:
            dict[str, Any]: JSON-ready mapping.
        """
        return {
            "contract_id": self.contract_id,
            "version": self.version,
            "canonical_hash": self.canonical_hash,
            "status": self.status,
            "owner_wp": self.owner_wp,
            "consumer_wps": list(self.consumer_wps),
        }


@dataclass(frozen=True)
class ReverificationTrigger:
    """A consumer's obligation to re-verify after a generation was superseded.

    Attributes:
        contract_id: The superseded generation.
        superseded_by: The generation that replaced it.
        consumer_wp: Work package that consumed the superseded generation.
        stale_on: Trigger token the consumer's `stale_on` axis must carry.
        required_replacement_wp: Named replacement work package the bump
            procedure requires (`06` §4.3 step 2). It must be registered in
            `02a`~`02d` before use; until then `CI-05b` reports it as a ghost.
    """

    contract_id: str
    superseded_by: str
    consumer_wp: str
    stale_on: str
    required_replacement_wp: str

    def as_dict(self) -> dict[str, str]:
        """Return the trigger in the index's serialized shape.

        Returns:
            dict[str, str]: JSON-ready mapping.
        """
        return {
            "contract_id": self.contract_id,
            "superseded_by": self.superseded_by,
            "consumer_wp": self.consumer_wp,
            "stale_on": self.stale_on,
            "required_replacement_wp": self.required_replacement_wp,
        }


@dataclass(frozen=True)
class FreezeOutcome:
    """Result of a freeze or a `@v(n+1)` issue.

    Attributes:
        record: The contract generation now recorded as frozen.
        superseded: Generation demoted to `SUPERSEDED`, if this was a bump.
        triggers: Re-verification obligations emitted for the consumers of the
            superseded generation. Empty for an initial freeze.
        already_frozen: True when the identical content was already frozen and
            no ledger event was appended.
    """

    record: ContractRecord
    superseded: str | None
    triggers: tuple[ReverificationTrigger, ...]
    already_frozen: bool


@dataclass(frozen=True)
class ConsumesAxis:
    """The registry's `consumes` axis, indexed both ways.

    Attributes:
        by_contract: Contract id to the work packages consuming it.
        by_wp: Work package to the contract ids it consumes.
    """

    by_contract: Mapping[str, tuple[str, ...]]
    by_wp: Mapping[str, tuple[str, ...]]


def load_consumes_axis(registry_path: Path) -> ConsumesAxis:
    """Read the registry's contract consumption axis.

    Records whose `wp` is not an issued work package id (`DEFERRED`) are
    dropped: a deferred requirement has no work package to start, so counting
    it as a consumer would make the axis disagree with every real query.

    Args:
        registry_path: Path to `registry/traceability.yaml`.

    Returns:
        ConsumesAxis: The axis indexed by contract and by work package.
    """
    document = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    by_contract: dict[str, set[str]] = {}
    by_wp: dict[str, set[str]] = {}
    for entry in document.get("entries", []):
        wp_id = str(entry.get("wp", ""))
        if not wp_id.startswith("WP-"):
            continue
        contract = entry.get("contract") or {}
        for contract_id in contract.get("consumes") or []:
            by_contract.setdefault(str(contract_id), set()).add(wp_id)
            by_wp.setdefault(wp_id, set()).add(str(contract_id))
    return ConsumesAxis(
        by_contract={key: tuple(sorted(value)) for key, value in by_contract.items()},
        by_wp={key: tuple(sorted(value)) for key, value in by_wp.items()},
    )


def fold_state(events: Iterable[ledger.LedgerEvent]) -> dict[str, tuple[str, str | None]]:
    """Replay the ledger into per-generation freeze state.

    Args:
        events: Ledger events in recorded order.

    Returns:
        dict[str, tuple[str, str | None]]: Contract id to `(status, hash)`.
    """
    state: dict[str, tuple[str, str | None]] = {}
    for event in events:
        if event.kind == ledger.FREEZE:
            state[event.contract_id] = (FROZEN, event.canonical_hash)
        elif event.kind == ledger.SUPERSEDE:
            _, content_hash = state.get(event.contract_id, (DRAFT, None))
            state[event.contract_id] = (SUPERSEDED, content_hash)
        elif event.kind == ledger.RETIRE:
            _, content_hash = state.get(event.contract_id, (DRAFT, None))
            state[event.contract_id] = (RETIRED, content_hash)
    return state


def build_index(store: ContractStore) -> dict[str, Any]:
    """Derive the whole index from the catalog, the registry and the ledger.

    Args:
        store: Locations to read from.

    Returns:
        dict[str, Any]: The index document.

    Raises:
        ContractViolationError: If the ledger chain is broken, or the ledger records
            a contract outside the closed namespace. Building an index over a
            tampered ledger would launder the tampering into a signed-looking
            artifact, so this refuses rather than reports.
    """
    events = ledger.read_ledger(store.ledger_path)
    chain_violations = ledger.verify_chain(events)
    if chain_violations:
        raise ContractViolationError(chain_violations[0])

    catalog = load_catalog(store.plan_root)
    axis = load_consumes_axis(store.registry_path)
    state = fold_state(events)

    for contract_id in state:
        require_in_namespace(parse_contract_id(contract_id), catalog)

    records = _build_records(catalog, state, axis)
    triggers = _build_triggers(events, catalog, axis)
    return {
        "version": INDEX_VERSION,
        "namespace": NAMESPACE,
        "canonical_source": str(CANONICAL_DOC),
        "ledger_head": ledger.head_digest(events),
        "contracts": [record.as_dict() for record in records],
        "reverification_triggers": [trigger.as_dict() for trigger in triggers],
    }


def write_index(store: ContractStore) -> dict[str, Any]:
    """Rebuild the index and persist it.

    Args:
        store: Locations to read from and write to.

    Returns:
        dict[str, Any]: The index document that was written.
    """
    index = build_index(store)
    ledger.write_atomic(store.index_path, json.dumps(index, indent=2, ensure_ascii=False) + "\n")
    return index


def verify_index(store: ContractStore) -> list[Violation]:
    """Check the persisted index against the sources it must reconstruct from.

    This is the static check that makes hand-editing `contract_index.json`
    pointless: the file is compared field by field against a fresh derivation,
    so an edited hash, an invented contract, or a doctored consumer list is a
    difference regardless of who wrote it or how.

    Args:
        store: Locations to read from.

    Returns:
        list[Violation]: Every difference found. Empty when the index is
            exactly what its sources produce.
    """
    events = ledger.read_ledger(store.ledger_path)
    chain_violations = ledger.verify_chain(events)
    if chain_violations:
        return chain_violations

    if not store.index_path.exists():
        return [
            Violation(
                rule="CI-09",
                severity=SEVERITY_BLOCKING,
                location=str(store.index_path),
                expected="a generated contract index",
                actual="file does not exist",
            )
        ]

    expected = build_index(store)
    actual = json.loads(store.index_path.read_text(encoding="utf-8"))
    return _diff_index(expected, actual, str(store.index_path))


def freeze_contract(
    store: ContractStore, contract_id: str, schema: Mapping[str, Any]
) -> FreezeOutcome:
    """Freeze a schema contract, or issue the next generation.

    Issuing `@v(n+1)` is the same operation as an initial freeze — `06` §4.3
    defines a change as the publication of a new generation, not as a separate
    edit mode — so this is the single entry point for both. A bump is a freeze
    whose version is one above a currently frozen generation, and it is the
    only path that emits re-verification triggers.

    The value locked is the schema's canonical projection hash (`canonical.py`),
    which is deliberately blind to documentation-only edits. A `CONTRACT_FROZEN`
    *glob* contract (`06` §3.2) is not a schema and is frozen by its byte-exact
    content hash instead — see `freeze_with_content_hash`.

    Args:
        store: Locations to read from and write to.
        contract_id: Contract generation to freeze.
        schema: Parsed contract schema whose canonical hash is being locked.

    Returns:
        FreezeOutcome: The recorded generation and any triggers it emitted.

    Raises:
        ContractViolationError: If the id is malformed, outside the namespace, would
            change an already-frozen generation, or skips the issuing order.
    """
    return freeze_with_content_hash(store, contract_id, canonical_hash(schema))


def freeze_with_content_hash(
    store: ContractStore, contract_id: str, content_hash: str
) -> FreezeOutcome:
    """Freeze a generation at an already-computed content hash.

    The freeze machinery — ledger append, index rewrite, trigger fan-out — does
    not care how the hash was derived, only that it is recorded once and never
    re-derived under the same generation. Both a schema's canonical hash
    (`freeze_contract`) and the byte-exact content hash of a `CONTRACT_FROZEN`
    glob converge here, so the ledger keeps one writer and one event shape.

    Args:
        store: Locations to read from and write to.
        contract_id: Contract generation to freeze.
        content_hash: The value to lock as this generation's `canonical_hash`.

    Returns:
        FreezeOutcome: The recorded generation and any triggers it emitted.

    Raises:
        ContractViolationError: If the id is malformed, outside the namespace, would
            change an already-frozen generation, or skips the issuing order.
    """
    ref = parse_contract_id(contract_id)
    catalog = load_catalog(store.plan_root)
    require_in_namespace(ref, catalog)

    events = ledger.read_ledger(store.ledger_path)
    chain_violations = ledger.verify_chain(events)
    if chain_violations:
        raise ContractViolationError(chain_violations[0])

    state = fold_state(events)
    pending = _plan_freeze(ref, content_hash, state)

    superseded = str(ref.at_version(ref.version - 1)) if ref.version > 1 else None
    if pending:
        events = ledger.append_events(store.ledger_path, events, pending)
    write_index(store)

    axis = load_consumes_axis(store.registry_path)
    triggers = tuple(_triggers_for(superseded, str(ref), axis)) if superseded is not None else ()
    definition = catalog[ref.name]
    record = ContractRecord(
        contract_id=str(ref),
        version=ref.version,
        canonical_hash=content_hash,
        status=FROZEN,
        owner_wp=definition.owner_wp,
        consumer_wps=axis.by_contract.get(str(ref), ()),
    )
    return FreezeOutcome(
        record=record,
        superseded=superseded,
        triggers=triggers,
        already_frozen=not pending,
    )


def retire_contract(store: ContractStore, contract_id: str) -> ContractRecord:
    """Close the consumption window on a superseded generation.

    `06` §4.3 step 4 retires the old generation only once every named
    replacement work package has landed; until then step 3 keeps the old
    consumption path alive. Whether they have landed is workflow state this
    package does not own, so the judgement is the caller's and this records it.

    Args:
        store: Locations to read from and write to.
        contract_id: Generation to retire.

    Returns:
        ContractRecord: The retired generation.

    Raises:
        ContractViolationError: If the generation is not currently superseded.
            Retiring a frozen generation would strand its consumers with no
            successor to move to.
    """
    ref = parse_contract_id(contract_id)
    catalog = load_catalog(store.plan_root)
    require_in_namespace(ref, catalog)

    events = ledger.read_ledger(store.ledger_path)
    chain_violations = ledger.verify_chain(events)
    if chain_violations:
        raise ContractViolationError(chain_violations[0])

    state = fold_state(events)
    status, content_hash = state.get(contract_id, (DRAFT, None))
    if status != SUPERSEDED:
        raise ContractViolationError(
            Violation(
                rule="CR-3",
                severity=SEVERITY_BLOCKING,
                location=contract_id,
                expected=f"{SUPERSEDED} — only a replaced generation may be retired",
                actual=f"{contract_id} is {status}",
            )
        )

    ledger.append_events(store.ledger_path, events, [(ledger.RETIRE, contract_id, None)])
    write_index(store)
    axis = load_consumes_axis(store.registry_path)
    return ContractRecord(
        contract_id=contract_id,
        version=ref.version,
        canonical_hash=content_hash,
        status=RETIRED,
        owner_wp=catalog[ref.name].owner_wp,
        consumer_wps=axis.by_contract.get(contract_id, ()),
    )


def check_wp_start(store: ContractStore, wp_id: str) -> list[Violation]:
    """Check that a work package may start given the contracts it consumes.

    `CR-2` forbids consuming a contract before it is frozen: a consumer that
    starts against a draft has read a schema that its producer may still
    change, and no later check can tell which version it implemented. The
    index is derived here rather than loaded, so a stale or edited
    `contract_index.json` cannot make a blocked start look permitted.

    Args:
        store: Locations to read from.
        wp_id: Work package attempting to start.

    Returns:
        list[Violation]: One entry per consumed contract that blocks the start.
            Empty when every consumed contract is frozen or superseded.
    """
    index = build_index(store)
    status_of = {str(record["contract_id"]): str(record["status"]) for record in index["contracts"]}
    axis = load_consumes_axis(store.registry_path)

    violations: list[Violation] = []
    for contract_id in axis.by_wp.get(wp_id, ()):
        location = f"{wp_id} consumes {contract_id}"
        status = status_of.get(contract_id)
        if status is None:
            violations.append(
                Violation(
                    rule="CR-2",
                    severity=SEVERITY_BLOCKING,
                    location=location,
                    expected="a contract generation registered in the index",
                    actual=f"{contract_id} is not registered",
                )
            )
        elif status not in CONSUMABLE_STATUSES:
            violations.append(
                Violation(
                    rule="CR-2",
                    severity=SEVERITY_BLOCKING,
                    location=location,
                    expected=f"status in {sorted(CONSUMABLE_STATUSES)} before start",
                    actual=f"{contract_id} is {status}",
                )
            )
    return violations


def _plan_freeze(
    ref: ContractRef, content_hash: str, state: Mapping[str, tuple[str, str | None]]
) -> list[tuple[str, str, str | None]]:
    """Decide which ledger events a freeze request should append.

    Args:
        ref: Generation being frozen.
        content_hash: Canonical hash of the submitted schema.
        state: Current folded ledger state.

    Returns:
        list[tuple[str, str, str | None]]: Events to append; empty when the
            identical content is already frozen.

    Raises:
        ContractViolationError: If the request would change a frozen generation or
            skip the issuing order.
    """
    contract_id = str(ref)
    status, frozen_hash = state.get(contract_id, (DRAFT, None))

    if status in {FROZEN, SUPERSEDED, RETIRED}:
        if status == FROZEN and frozen_hash == content_hash:
            return []
        raise ContractViolationError(
            Violation(
                rule="CI-09",
                severity=SEVERITY_BLOCKING,
                location=contract_id,
                expected=f"{contract_id} is {status}; changes are issued as "
                f"{ref.at_version(ref.version + 1)}",
                actual=f"content hash {content_hash} replacing {frozen_hash}",
            )
        )

    if ref.version == 1:
        return [(ledger.FREEZE, contract_id, content_hash)]

    predecessor = str(ref.at_version(ref.version - 1))
    previous_status, _ = state.get(predecessor, (DRAFT, None))
    if previous_status != FROZEN:
        raise ContractViolationError(
            Violation(
                rule="CR-3",
                severity=SEVERITY_BLOCKING,
                location=contract_id,
                expected=f"{predecessor} frozen before {contract_id} is issued",
                actual=f"{predecessor} is {previous_status}",
            )
        )
    return [
        (ledger.SUPERSEDE, predecessor, None),
        (ledger.FREEZE, contract_id, content_hash),
    ]


def _build_records(
    catalog: Mapping[str, ContractDefinition],
    state: Mapping[str, tuple[str, str | None]],
    axis: ConsumesAxis,
) -> list[ContractRecord]:
    """Assemble one record per known contract generation.

    Every catalog entry is emitted even before its producer freezes it, so the
    index answers "are all 13 registered" from day one and a consumer asking
    about an unfrozen contract gets `DRAFT` rather than a missing key.

    Args:
        catalog: Canonical definitions keyed by bare name.
        state: Folded ledger state.
        axis: Registry consumes axis.

    Returns:
        list[ContractRecord]: Records ordered by name then version.
    """
    generations: dict[str, set[int]] = {name: {1} for name in catalog}
    for contract_id in state:
        ref = parse_contract_id(contract_id)
        generations[ref.name].add(ref.version)

    records: list[ContractRecord] = []
    for name in sorted(generations):
        definition = catalog[name]
        for version in sorted(generations[name]):
            contract_id = str(ContractRef(name=name, version=version))
            status, content_hash = state.get(contract_id, (DRAFT, None))
            records.append(
                ContractRecord(
                    contract_id=contract_id,
                    version=version,
                    canonical_hash=content_hash,
                    status=status,
                    owner_wp=definition.owner_wp,
                    consumer_wps=axis.by_contract.get(contract_id, ()),
                )
            )
    return records


def _build_triggers(
    events: Iterable[ledger.LedgerEvent],
    catalog: Mapping[str, ContractDefinition],
    axis: ConsumesAxis,
) -> list[ReverificationTrigger]:
    """Derive re-verification triggers from recorded supersede events.

    Triggers are derived rather than stored so they cannot drift from the
    ledger that caused them, and so a consumer added to the registry after a
    bump still receives its obligation on the next rebuild.

    Args:
        events: Ledger events in recorded order.
        catalog: Canonical definitions keyed by bare name.
        axis: Registry consumes axis.

    Returns:
        list[ReverificationTrigger]: One trigger per consumer per supersede.
    """
    triggers: list[ReverificationTrigger] = []
    for event in events:
        if event.kind != ledger.SUPERSEDE:
            continue
        ref = parse_contract_id(event.contract_id)
        if ref.name not in catalog:
            continue
        successor = str(ref.at_version(ref.version + 1))
        triggers.extend(_triggers_for(event.contract_id, successor, axis))
    return triggers


def _triggers_for(
    superseded_id: str, successor_id: str, axis: ConsumesAxis
) -> list[ReverificationTrigger]:
    """Build triggers for every consumer of a superseded generation.

    Args:
        superseded_id: The superseded contract id.
        successor_id: The generation replacing it.
        axis: Registry consumes axis.

    Returns:
        list[ReverificationTrigger]: One trigger per consuming work package.
    """
    ref = parse_contract_id(superseded_id)
    successor = parse_contract_id(successor_id)
    return [
        ReverificationTrigger(
            contract_id=superseded_id,
            superseded_by=successor_id,
            consumer_wp=consumer_wp,
            stale_on=f"CTR-{ref.name}:MAJOR_BUMP",
            required_replacement_wp=f"{consumer_wp}M{successor.version}",
        )
        for consumer_wp in axis.by_contract.get(superseded_id, ())
    ]


def _diff_index(
    expected: Mapping[str, Any], actual: Mapping[str, Any], location: str
) -> list[Violation]:
    """Compare a persisted index against a freshly derived one.

    Args:
        expected: Index derived from the sources.
        actual: Index read from disk.
        location: Path of the persisted index, for reporting.

    Returns:
        list[Violation]: One entry per differing field.
    """
    violations: list[Violation] = []
    for key in ("version", "namespace", "canonical_source", "ledger_head"):
        if actual.get(key) != expected[key]:
            violations.append(
                Violation(
                    rule="CI-09",
                    severity=SEVERITY_BLOCKING,
                    location=f"{location}#{key}",
                    expected=str(expected[key]),
                    actual=str(actual.get(key)),
                )
            )

    expected_records = {str(row["contract_id"]): row for row in expected["contracts"]}
    actual_records = {str(row.get("contract_id")): row for row in actual.get("contracts", [])}
    for contract_id in sorted(set(expected_records) | set(actual_records)):
        if contract_id not in actual_records:
            violations.append(
                Violation(
                    rule="CI-09",
                    severity=SEVERITY_BLOCKING,
                    location=f"{location}#contracts/{contract_id}",
                    expected="record present",
                    actual="record missing",
                )
            )
            continue
        if contract_id not in expected_records:
            violations.append(
                Violation(
                    rule="CI-03c",
                    severity=SEVERITY_BLOCKING,
                    location=f"{location}#contracts/{contract_id}",
                    expected="no such record — it is not derivable from the sources",
                    actual="record present",
                )
            )
            continue
        violations.extend(
            _diff_record(
                expected_records[contract_id],
                actual_records[contract_id],
                f"{location}#contracts/{contract_id}",
            )
        )

    expected_triggers = [
        json.dumps(row, sort_keys=True) for row in expected["reverification_triggers"]
    ]
    actual_triggers = [
        json.dumps(row, sort_keys=True) for row in actual.get("reverification_triggers", [])
    ]
    if expected_triggers != actual_triggers:
        violations.append(
            Violation(
                rule="CI-09",
                severity=SEVERITY_BLOCKING,
                location=f"{location}#reverification_triggers",
                expected=f"{len(expected_triggers)} triggers derived from the ledger",
                actual=f"{len(actual_triggers)} triggers recorded",
            )
        )
    return violations


def _diff_record(
    expected: Mapping[str, Any], actual: Mapping[str, Any], location: str
) -> list[Violation]:
    """Compare one persisted contract record against its derivation.

    Args:
        expected: Derived record.
        actual: Persisted record.
        location: Path into the index document, for reporting.

    Returns:
        list[Violation]: One entry per differing field.
    """
    rules = {
        "version": "CI-09",
        "canonical_hash": "CI-09",
        "status": "CI-09",
        "owner_wp": "CI-03",
        "consumer_wps": "CR-5",
    }
    violations: list[Violation] = []
    for field, rule in rules.items():
        if actual.get(field) != expected[field]:
            violations.append(
                Violation(
                    rule=rule,
                    severity=SEVERITY_BLOCKING,
                    location=f"{location}/{field}",
                    expected=str(expected[field]),
                    actual=str(actual.get(field)),
                )
            )
    return violations
