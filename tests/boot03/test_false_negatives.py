"""Mutation testing: a rule scoring zero detections is rejected.

`02a` §−2.3 acceptance ⑪. Fixtures prove a rule *can* fire on the one violation
its author imagined. This test injects random mutations into a clean corpus and
records how often the rule set notices, which is a different question — it is the
one that catches a rule matching only the exact shape of its own fixture.

The recorded rate is asserted per mutation family rather than per rule: a mutation
of the `gate` axis should be caught by whichever rule owns that axis, and demanding
that every rule catch every mutation would only reward over-broad rules.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from typing import Any

import pytest

from registry.checks import JUDGE_RANGE
from registry.checks.corpus import Corpus
from registry.checks.fixtures import REPO_ROOT, corpus, record

# Prose scanning is scoped to the spine document so that the real corpus's own
# dangling citations cannot masquerade as detections of an injected mutation.
SPINE_DOC = REPO_ROOT / "docs" / "plan" / "00-실행계획-개요.md"

DECLARED_REQUIREMENTS = frozenset({"FR-CAM-001", "FR-CAM-006"})

MUTATION_SEED = 20260720
MUTATIONS_PER_FAMILY = 12

# Every mutation family must be detected every time: each one breaks an axis that
# some rule owns outright, so a miss is a hole rather than a near-miss.
REQUIRED_DETECTION_RATE = 1.0


def _mutate_gate(rng: random.Random) -> dict[str, Any]:
    return record(gate=[], negative_branch=[])


def _mutate_shape(rng: random.Random) -> dict[str, Any]:
    shape = rng.choice(["SHAPE-MS", "SHAPE-HG", "SHAPE-IG"])
    return record(workflow=shape, exec_class="AI-offline")


def _mutate_contract(rng: random.Random) -> dict[str, Any]:
    invented = rng.choice(["CT-RT-BUDGET@v1", "CTR-NOPE@v1", "CT-POLICY-COMPAT@v2"])
    return record(contract={"consumes": [invented], "produces": ["CTR-PRIM@v1"]})


def _mutate_floating_version(rng: random.Random) -> dict[str, Any]:
    operator = rng.choice(["^", "~", "*"])
    return record(contract={"consumes": [f"CTR-ACT@{operator}v1"], "produces": []})


def _mutate_cg_state(rng: random.Random) -> dict[str, Any]:
    state = rng.choice(["RETRY_WITH_VARIANT", "DEGRADED_ACCEPTED", "FAIL_BLOCKING", "SUPERSEDED"])
    return record(negative_branch=[{"gate": "CG-3A-00a", "on": state, "action": "x"}])


def _mutate_cg_letter(rng: random.Random) -> dict[str, Any]:
    letter = rng.choice("uvwxyz")
    gate = f"CG-3A-00{letter}"
    return record(gate=[gate], negative_branch=[{"gate": gate, "on": "FAIL", "action": "x"}])


def _mutate_sealed_gate(rng: random.Random) -> dict[str, Any]:
    gate = rng.choice(["M-8", "PG-RT-001"])
    return record(gate=[gate], negative_branch=[{"gate": gate, "on": "FAIL", "action": "x"}])


def _mutate_phantom_req(rng: random.Random) -> dict[str, Any]:
    return record(req=f"FR-ZZZ-{rng.randint(100, 999)}")


def _mutate_dangling_section(rng: random.Random) -> dict[str, Any]:
    return record(spec_ref=f"06#{rng.randint(70, 99)}.{rng.randint(1, 9)}")


def _mutate_measurement_owns(rng: random.Random) -> dict[str, Any]:
    return record(
        wp="WP-0B-07",
        workflow="SHAPE-MS",
        exec_class="AI-on-HW",
        owns=[{"glob": "backend/motors/**", "mode": "EXCLUSIVE"}],
        gate=["PG-RID-001"],
        negative_branch=[{"gate": "PG-RID-001", "on": "FAIL_BLOCKING", "action": "halt"}],
    )


MUTATION_FAMILIES: tuple[tuple[str, Callable[[random.Random], dict[str, Any]]], ...] = (
    ("empty-gate", _mutate_gate),
    ("shape-class-mismatch", _mutate_shape),
    ("invented-contract", _mutate_contract),
    ("floating-version", _mutate_floating_version),
    ("cg-state-machine", _mutate_cg_state),
    ("cg-letter-overrun", _mutate_cg_letter),
    ("sealed-gate-id", _mutate_sealed_gate),
    ("phantom-requirement", _mutate_phantom_req),
    ("dangling-section", _mutate_dangling_section),
    ("measurement-owns", _mutate_measurement_owns),
)


def _signatures(records: tuple[dict[str, Any], ...]) -> set[tuple[str, str, str]]:
    """Run the judged rule set and return the identity of every finding.

    Args:
        records: Registry records the corpus presents.

    Returns:
        (set[tuple[str, str, str]]) Rule id, subject and reason per finding.
    """
    # Pinned rather than derived from the records: the fixture helper's default
    # derives the declared set *from* the corpus, which would make every invented
    # requirement declared by construction and CI-01b impossible to fail.
    built: Corpus = corpus(
        records,
        tracked_files=(),
        artifact_tree=(),
        plan_paths=(SPINE_DOC,),
        spec_requirements=DECLARED_REQUIREMENTS,
    )
    return {
        (module.RULE_ID, finding.req_or_wp, finding.reason)
        for module in JUDGE_RANGE
        for finding in module.run(built).findings
    }


BASELINE = _signatures((record(),))


@pytest.mark.parametrize(
    ("family", "mutate"), MUTATION_FAMILIES, ids=[name for name, _ in MUTATION_FAMILIES]
)
def test_mutation_family_is_detected(family: str, mutate) -> None:
    """Randomly injected mutations of this family are caught by the rule set.

    Detection means a finding the unmutated baseline does not already produce, so
    a rule that is red for an unrelated reason cannot be credited with catching
    the mutation.
    """
    rng = random.Random(f"{MUTATION_SEED}-{family}")
    detections = sum(
        1 for _ in range(MUTATIONS_PER_FAMILY) if _signatures((mutate(rng),)) - BASELINE
    )
    rate = detections / MUTATIONS_PER_FAMILY
    assert rate >= REQUIRED_DETECTION_RATE, (
        f"{family}: detection rate {rate:.0%} ({detections}/{MUTATIONS_PER_FAMILY}); "
        "a rule that scores zero on its own axis is rejected"
    )


def test_baseline_is_recorded_not_assumed() -> None:
    """The baseline is small enough that detections are meaningfully above it."""
    assert len(BASELINE) <= len(tuple(JUDGE_RANGE)), (
        f"baseline carries {len(BASELINE)} findings; detection above it would be "
        f"too weak a signal: {sorted(BASELINE)}"
    )
