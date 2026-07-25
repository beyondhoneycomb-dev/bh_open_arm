"""CG-4C-05d — both conditions record their per-episode initial-state seeds.

`FR-SIM-056` requires the initial-state seed to be recorded per episode. A condition arm
that dropped its seeds would let an irreproducible rollout into the protocol, so
`ConditionArm` refuses a report with no seeds, and both conditions' seeds appear in the
rendered report.
"""

from __future__ import annotations

import dataclasses

from backend.eval.protocol import (
    Condition,
    ConditionArm,
    ConditionSetError,
    DualConditionReport,
    DualConditionSet,
)
from tests.wp4c05.support import arm, defined_protocol


def test_both_arms_record_seeds() -> None:
    """A matched pair records seeds on both conditions (CG-4C-05d)."""
    nominal = arm(Condition.NOMINAL, 15, 20, seed_base=0)
    perturbed = arm(Condition.PERTURBED, 10, 20, seed_base=100)
    assert len(nominal.seeds) == 20
    assert len(perturbed.seeds) == 20
    assert nominal.seeds != perturbed.seeds


def test_seeds_appear_in_rendered_report() -> None:
    """The rendered report prints each condition's seeds (CG-4C-05d)."""
    nominal = arm(Condition.NOMINAL, 15, 20, seed_base=0)
    perturbed = arm(Condition.PERTURBED, 10, 20, seed_base=100)
    rendered = DualConditionReport.of(
        DualConditionSet.create(nominal, perturbed, defined_protocol())
    ).render()
    assert "시드" in rendered
    assert str(nominal.seeds[0]) in rendered
    assert str(perturbed.seeds[0]) in rendered


def test_arm_with_no_seeds_is_refused() -> None:
    """An arm whose report records no seeds is refused (FR-SIM-056 / CG-4C-05d)."""
    good = arm(Condition.NOMINAL, 15, 20)
    seedless_report = dataclasses.replace(good.report, seeds=())
    try:
        ConditionArm(
            condition=Condition.NOMINAL,
            report=seedless_report,
            success_criterion_id="crit-1",
        )
    except ConditionSetError as error:
        assert "seed" in str(error).lower()
        return
    raise AssertionError("an arm with no recorded seeds must be refused (CG-4C-05d)")


def test_nominal_only_arm_records_seeds() -> None:
    """Even on the NOMINAL-only deferred path, the single condition records its seeds."""
    nominal = arm(Condition.NOMINAL, 15, 20, seed_base=7)
    assert nominal.seeds[0] == 7
    assert len(nominal.seeds) == 20
