"""Load and drift-check the CTR-OWN@v1 contract document.

`ownership/registry.yaml` freezes the span model and encodes the `06` §3.2
handover arrows as ordinal spans. That encoding is the one place this contract
holds data of its own, so it is also the one place that could silently disagree
with `06` §3.2. `check_drift` closes that gap: it re-reads the arrows from the
plan document and refuses any divergence, which keeps the frozen view honest
without turning it into a second source of ownership truth.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ownership.model import Claim, Span

CONTRACT_ID = "CTR-OWN@v1"
CONTRACT_PATH = Path("ownership") / "registry.yaml"

_SPAN_BOUND_COUNT = 2


class ContractError(RuntimeError):
    """Raised when the CTR-OWN@v1 document is malformed or has drifted."""


def load_contract(path: Path) -> dict[str, Any]:
    """Read and structurally validate the CTR-OWN@v1 document.

    Args:
        path: Path to `ownership/registry.yaml`.

    Returns:
        (dict[str, Any]) The parsed contract mapping.

    Raises:
        ContractError: If the file does not parse to a mapping or declares a
            contract id other than `CTR-OWN@v1`.
    """
    loaded: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ContractError(f"{path} did not parse to a mapping")
    declared = loaded.get("contract")
    if declared != CONTRACT_ID:
        raise ContractError(f"{path} declares contract {declared!r}, expected {CONTRACT_ID!r}")
    return loaded


def declared_claims(contract: dict[str, Any]) -> tuple[Claim, ...]:
    """Return the ownership claims the contract's handover chains encode.

    Each `handover_chains[]` entry names a glob and an ordered list of
    `{owner_wp, span}` pairs; the span pair `[start, end]` is read as the
    half-open interval `[start, end)`.

    Args:
        contract: The parsed contract mapping.

    Returns:
        (tuple[Claim, ...]) One claim per (glob, owner) the contract freezes.

    Raises:
        ContractError: If a chain entry is malformed.
    """
    claims: list[Claim] = []
    for chain in contract.get("handover_chains", []) or []:
        glob = chain.get("glob")
        if not isinstance(glob, str):
            raise ContractError(f"handover chain has no glob: {chain!r}")
        exclusive = bool(chain.get("exclusive", True))
        for entry in chain.get("spans", []) or []:
            owner = entry.get("owner_wp")
            bounds = entry.get("span")
            if not isinstance(owner, str):
                raise ContractError(f"span entry has no owner_wp: {entry!r}")
            if not isinstance(bounds, list) or len(bounds) != _SPAN_BOUND_COUNT:
                raise ContractError(f"span for {owner} is not a [start, end] pair: {bounds!r}")
            claims.append(
                Claim(
                    path_glob=glob,
                    owner_wp=owner,
                    exclusive=exclusive,
                    span=Span(int(bounds[0]), int(bounds[1])),
                )
            )
    return tuple(claims)


def declared_chains(contract: dict[str, Any]) -> tuple[tuple[str, ...], ...]:
    """Return the ordered owner sequences the contract declares.

    Args:
        contract: The parsed contract mapping.

    Returns:
        (tuple[tuple[str, ...], ...]) One ordered `WP-*` tuple per handover chain,
        in the span order the document lists.
    """
    chains: list[tuple[str, ...]] = []
    for chain in contract.get("handover_chains", []) or []:
        owners = tuple(entry.get("owner_wp") for entry in chain.get("spans", []) or [])
        if all(isinstance(owner, str) for owner in owners) and len(owners) > 1:
            chains.append(owners)
    return tuple(chains)


def check_drift(
    contract: dict[str, Any], chains_from_doc: tuple[tuple[str, ...], ...]
) -> tuple[str, ...]:
    """Report where the contract's chains disagree with `06` §3.2.

    The comparison is on the set of ordered chains: chain order within the
    document is irrelevant, but the succession order *inside* a chain is the
    handover direction and must match. A chain the document declares that the
    contract omits, or vice versa, is a drift.

    Args:
        contract: The parsed contract mapping.
        chains_from_doc: Ordered chains read from `06` §3.2
            (`ownership.prover.read_handover_chains`).

    Returns:
        (tuple[str, ...]) One message per divergence; empty when they agree.
    """
    declared = set(declared_chains(contract))
    from_doc = set(chains_from_doc)
    messages: list[str] = []
    for chain in sorted(from_doc - declared):
        messages.append(f"06 §3.2 declares handover {' → '.join(chain)} that CTR-OWN@v1 omits")
    for chain in sorted(declared - from_doc):
        messages.append(f"CTR-OWN@v1 declares handover {' → '.join(chain)} that 06 §3.2 does not")
    return tuple(messages)
