"""Namespace closure and id grammar — WP-BOOT-05 acceptance ④ and ⑤."""

from __future__ import annotations

from pathlib import Path

import pytest

from registry.contracts.catalog import CONTRACT_COUNT, load_catalog, parse_contract_id
from registry.contracts.index import freeze_contract
from registry.contracts.violations import ContractViolationError
from tests.boot05.conftest import REPO_ROOT, schema_with

# `06` §4.1b names three ids a previous revision invented. They are artifacts,
# and re-registering any of them must fail rather than quietly extend the
# namespace.
INVENTED_CONTRACTS = [
    "CTR-SCHEDULERMAILBOX@v1",
    "CTR-RTBUDGET@v1",
    "CTR-POLICYCOMPAT@v1",
    "CTR-EVERYTHING@v1",
]

MALFORMED_IDS = [
    "CTR-ACT@1.2.0",
    "CTR-ACT@v1.2",
    "CTR-ACT@v1.0.0",
    "CTR-ACT@^v1",
    "CTR-ACT@~v1",
    "CTR-ACT@latest",
    "CTR-ACT@*",
    "CTR-ACT@v0",
    "CTR-ACT",
    "ctr-act@v1",
    "CT-ACT@v1",
    "ACT@v1",
    "CTR-ACT@v1 ",
]


def test_catalog_declares_exactly_thirteen_contracts() -> None:
    """The closed namespace has the size `06` §4.1 fixes it at."""
    assert len(load_catalog(REPO_ROOT)) == CONTRACT_COUNT


def test_every_canonical_name_is_a_parseable_id() -> None:
    """Each catalog entry round-trips through the id grammar."""
    for name, definition in load_catalog(REPO_ROOT).items():
        assert parse_contract_id(str(definition.ref)).name == name


@pytest.mark.parametrize("contract_id", MALFORMED_IDS)
def test_non_generation_ids_are_rejected(contract_id: str) -> None:
    """Semver and range notations are not contract ids (acceptance ⑤)."""
    with pytest.raises(ContractViolationError) as raised:
        parse_contract_id(contract_id)
    assert raised.value.violation.rule == "CI-08"


def test_generation_id_is_accepted() -> None:
    """The one legal notation still parses — the grammar is not blanket-deny."""
    ref = parse_contract_id("CTR-ACT@v2")
    assert (ref.name, ref.version) == ("ACT", 2)


@pytest.mark.parametrize("contract_id", INVENTED_CONTRACTS)
def test_contract_outside_the_thirteen_is_rejected(store, contract_id: str) -> None:
    """Registering a non-contract is refused as an artifact (acceptance ④)."""
    with pytest.raises(ContractViolationError) as raised:
        freeze_contract(store, contract_id, schema_with("a"))
    assert raised.value.violation.rule == "CI-03c"
    assert not store.ledger_path.exists()


def test_semver_id_never_reaches_the_ledger(store) -> None:
    """A rejected id leaves no trace — rejection is not a partial write."""
    with pytest.raises(ContractViolationError):
        freeze_contract(store, "CTR-ACT@1.2.0", schema_with("a"))
    assert not store.ledger_path.exists()


def test_every_canonical_contract_can_be_registered(store) -> None:
    """All 13 freeze and each carries a distinct hash (acceptance ①)."""
    catalog = load_catalog(REPO_ROOT)
    hashes = {}
    for name in catalog:
        outcome = freeze_contract(store, f"CTR-{name}@v1", schema_with(f"field_{name.lower()}"))
        hashes[name] = outcome.record.canonical_hash

    assert len(hashes) == CONTRACT_COUNT
    assert len(set(hashes.values())) == CONTRACT_COUNT
    assert all(value is not None for value in hashes.values())


def test_truncated_canonical_table_is_rejected(tmp_path: Path, store) -> None:
    """A catalog that lost a row fails loudly instead of shrinking silently."""
    source = (REPO_ROOT / "docs/plan/01-의존성-DAG-및-병렬화.md").read_text(encoding="utf-8")
    truncated = source.replace(
        "| `CTR-REC@v1` | **recorder 스키마** | `WP-3A-05` | Wave 3B 진입 |", "| x | x | x | x |", 1
    )
    doctored_root = tmp_path / "doctored"
    doctored = doctored_root / "docs/plan/01-의존성-DAG-및-병렬화.md"
    doctored.parent.mkdir(parents=True)
    doctored.write_text(truncated, encoding="utf-8")

    with pytest.raises(ContractViolationError) as raised:
        load_catalog(doctored_root)
    assert raised.value.violation.rule == "CI-03c"
    assert "12" in raised.value.violation.actual
