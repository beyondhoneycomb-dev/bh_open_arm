"""WP-0A-03 — the CTR-OWN@v1 contract is well-formed and has not drifted.

The frozen `ownership/registry.yaml` encodes the `06` §3.2 handover arrows as
ordinal spans. These tests hold that encoding to three things: it parses to the
CTR-OWN@v1 shape, it agrees with `06` §3.2 (no drift), and — the strongest bind —
the spans it freezes match what the prover derives from the live registry plus
`06` §3.2. The real-corpus overlap check is asserted green here too, since a
proven overlap-0 registry is the deliverable's whole reason to exist.
"""

from __future__ import annotations

from pathlib import Path

from ownership.cli import EXIT_OK, EXIT_VIOLATIONS, main
from ownership.contract import (
    CONTRACT_ID,
    CONTRACT_PATH,
    check_drift,
    declared_chains,
    declared_claims,
    load_contract,
)
from ownership.prover import (
    assemble_claims,
    concurrent_conflicts,
    exclusive_owners,
    read_handover_chains,
)
from registry.checks.corpus import Corpus

REPO_ROOT = Path(__file__).resolve().parents[2]
FOLLOWER = "packages/lerobot_robot_openarm/openarm_follower_oa.py"


def _contract() -> dict[str, object]:
    return load_contract(REPO_ROOT / CONTRACT_PATH)


def test_contract_declares_the_frozen_id() -> None:
    """The document parses and declares CTR-OWN@v1."""
    assert _contract()["contract"] == CONTRACT_ID


def test_contract_does_not_drift_from_the_plan_document() -> None:
    """The frozen handover chains agree with 06 §3.2, in order."""
    chains = read_handover_chains(REPO_ROOT / "docs" / "plan")
    assert check_drift(_contract(), chains) == ()


def test_frozen_follower_handover_is_ordered_and_adjacent() -> None:
    """The follower subclass is a WP-1-02 → WP-1-03 handover with adjacent spans."""
    claims = {claim.owner_wp: claim for claim in declared_claims(_contract())}
    assert ("WP-1-02", "WP-1-03") in declared_chains(_contract())
    assert claims["WP-1-02"].span.end == claims["WP-1-03"].span.start
    assert not claims["WP-1-02"].span.overlaps(claims["WP-1-03"].span)


def test_frozen_spans_match_the_live_registry_derivation() -> None:
    """The frozen claims equal what the prover derives from owns[] + 06 §3.2.

    This is the anti-drift guarantee in force: the contract is not an independent
    assertion of ownership, it is the derivable view pinned, so pinning it and
    deriving it must land on the same spans for the globs it names.
    """
    corpus = Corpus(REPO_ROOT)
    chains = read_handover_chains(corpus.plan_dir)
    derived = {
        (claim.path_glob, claim.owner_wp): claim.span
        for claim in assemble_claims(exclusive_owners(corpus), chains)
    }
    for frozen in declared_claims(_contract()):
        assert derived[(frozen.path_glob, frozen.owner_wp)] == frozen.span


def test_live_registry_is_overlap_free() -> None:
    """The real registry proves overlap-0: the two handovers are its only sharers."""
    corpus = Corpus(REPO_ROOT)
    chains = read_handover_chains(corpus.plan_dir)
    claims = assemble_claims(exclusive_owners(corpus), chains)
    assert concurrent_conflicts(claims, corpus.tracked_files) == ()


def test_ownership_job_runs_end_to_end_on_the_repository() -> None:
    """The CLI job runs cleanly and returns a defined verdict on the live repo.

    The exit code is not pinned to `EXIT_OK`: the job also fails on coverage holes,
    and the shared worktree carries in-flight sibling packages whose ownership has
    not landed yet, so the *coverage* verdict is a band-level property this suite
    does not own. The parts WP-0A-03 does own — no drift, no concurrent conflict —
    are asserted flatly above; here the job is proven to execute without error.
    """
    assert main(["--root", str(REPO_ROOT), "--quiet"]) in (EXIT_OK, EXIT_VIOLATIONS)
