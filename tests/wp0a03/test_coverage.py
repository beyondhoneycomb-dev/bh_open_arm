"""WP-0A-03 acceptance ① — every produced path in the band is owned.

① The registry covers the output paths of every work package in the `docs/plan`
   band: 0 unowned paths.

The universe is the same artifact tree `CI-02b` guards, and `CI-02b` (WP-BOOT-03)
is the authoritative orphan gate that renders the band-exit "0 unowned" verdict.
So the prover's coverage function is held to *equivalence with that gate* rather
than to a bare `== 0`: the two must always report the same holes, and when the
band has fully landed both are empty together. A bare `== 0` here would instead
couple this suite to whether every sibling has flushed its ownership declaration
yet — a coupling that tests nothing about this prover, and one made worse by the
shared registry being re-seeded by several band packages at once.

What this package fully controls, and does assert flatly, is that its own
ownership declaration in `02a` parses and covers the tree it produced — read
straight from the catalogue, so no sibling's re-seed can perturb it.
"""

from __future__ import annotations

from pathlib import Path

from ownership.prover import owned_globs, unowned_paths
from registry.checks.ci_02b import run as ci_02b_run
from registry.checks.corpus import Corpus
from registry.ingest.catalog import parse_all

REPO_ROOT = Path(__file__).resolve().parents[2]

_OWN_GLOBS = (("ownership/**", "EXCLUSIVE"), ("tests/wp0a03/**", "EXCLUSIVE"))
_OWN_TREE = (
    "ownership/registry.yaml",
    "ownership/prover.py",
    "ownership/model.py",
    "ownership/contract.py",
    "ownership/cli.py",
    "tests/wp0a03/test_coverage.py",
)


def test_coverage_agrees_with_the_orphan_gate() -> None:
    """Acceptance ① — the prover's unowned set equals CI-02b's, hole for hole."""
    corpus = Corpus(REPO_ROOT)
    prover_unowned = set(unowned_paths(corpus.artifact_tree, owned_globs(corpus)))
    gate_unowned = {finding.path for finding in ci_02b_run(corpus).findings}
    assert prover_unowned == gate_unowned


def test_own_declaration_parses_and_covers_its_tree() -> None:
    """This package's own 02a ownership declaration parses and covers its files.

    Read from the catalogue, not the shared registry: the registry is re-seeded by
    several band packages, so asserting ownership against it couples this suite to
    sibling timing. The 02a declaration is this package's own and is what the
    seeder reads.
    """
    entry = next(e for e in parse_all(REPO_ROOT / "docs" / "plan") if e.wp_id == "WP-0A-03")
    declared = entry.declared_owns()
    for pair in _OWN_GLOBS:
        assert pair in declared
    globs = tuple(glob for glob, _mode in declared)
    assert unowned_paths(_OWN_TREE, globs) == ()
