"""The ownership-verification job: prove overlap-0 over the real registry.

This is the `소유권 검증 CI 잡` of `WP-0A-03`. It assembles the CTR-OWN@v1 claim
view from the live registry and `06` §3.2, then runs the three checks whose green
is the precondition for any `SHAPE-IM` fan-out wider than one:

  - the contract has not drifted from `06` §3.2 (handover arrows still agree);
  - no two exclusive claims concurrently own a shared file (overlap checker);
  - every produced file is owned (coverage — no accountability holes).

Exit status is the contract: non-zero on any drift, conflict, or unowned path,
so a caller can gate on it. The claim view is printed either way, because a run
that found nothing and a run that never happened must not look alike.

Usage:
    python -m ownership.cli                 # verify the repository at cwd
    python -m ownership.cli --root PATH     # verify a repository elsewhere
    python -m ownership.cli --quiet         # verdict only, no claim listing
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ownership.contract import CONTRACT_PATH, check_drift, load_contract
from ownership.prover import (
    assemble_claims,
    concurrent_conflicts,
    exclusive_owners,
    owned_globs,
    read_handover_chains,
    unowned_paths,
)
from registry.checks.corpus import Corpus

EXIT_OK = 0
EXIT_VIOLATIONS = 1


def main(argv: list[str] | None = None) -> int:
    """Run the ownership-verification job and report.

    Args:
        argv: Command-line arguments, defaulting to `sys.argv[1:]`.

    Returns:
        (int) Process exit status; non-zero on any drift, conflict, or unowned
        path.
    """
    parser = argparse.ArgumentParser(prog="oa-ownership", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repository root")
    parser.add_argument("--quiet", action="store_true", help="print the verdict only")
    args = parser.parse_args(argv)

    corpus = Corpus(args.root)
    chains = read_handover_chains(corpus.plan_dir)
    claims = assemble_claims(exclusive_owners(corpus), chains)
    conflicts = concurrent_conflicts(claims, corpus.tracked_files)
    orphans = unowned_paths(corpus.artifact_tree, owned_globs(corpus))

    contract = load_contract(args.root / CONTRACT_PATH)
    drift = check_drift(contract, chains)

    if not args.quiet:
        for claim in claims:
            print(f"CLAIM   {claim.owner_wp:<10} {claim.span.label():<8} {claim.path_glob}")

    for message in drift:
        print(f"DRIFT   {message}")
    for conflict in conflicts:
        print(f"CONFLICT {conflict.as_line()}")
    for path in orphans:
        print(f"UNOWNED {path}")

    green = not (drift or conflicts or orphans)
    print(
        f"\nCTR-OWN@v1: {len(claims)} claim(s), {len(conflicts)} conflict(s), "
        f"{len(orphans)} unowned, {len(drift)} drift — {'GREEN' if green else 'BLOCKED'}"
    )
    return EXIT_OK if green else EXIT_VIOLATIONS


if __name__ == "__main__":
    sys.exit(main())
