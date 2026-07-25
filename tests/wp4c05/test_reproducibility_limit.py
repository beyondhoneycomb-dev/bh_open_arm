"""CG-4C-05e — the PERTURBED reproducibility limit is stated in the report.

`02c` §3.5 trade-off 2: recording the seed does not make a perturbed set as reproducible
as a nominal one, because the seed does not place the objects — a human does — and the
plan refuses to hide that. The report states the limit whether the perturbed condition
is measured or deferred, because the caveat is a property of the perturbed condition
itself, not of any one run.
"""

from __future__ import annotations

from backend.eval.protocol import (
    Condition,
    DualConditionReport,
    DualConditionSet,
)
from backend.eval.protocol.constants import PERTURBED_REPRODUCIBILITY_LIMIT
from tests.wp4c05.support import arm, deferred_protocol, defined_protocol


def test_limit_stated_when_gap_measured() -> None:
    """A measured (matched-pair) report states the PERTURBED reproducibility limit."""
    nominal = arm(Condition.NOMINAL, 16, 20, seed_base=0)
    perturbed = arm(Condition.PERTURBED, 10, 20, seed_base=100)
    report = DualConditionReport.of(DualConditionSet.create(nominal, perturbed, defined_protocol()))
    assert report.reproducibility_limit == PERTURBED_REPRODUCIBILITY_LIMIT
    assert PERTURBED_REPRODUCIBILITY_LIMIT in report.render()


def test_limit_stated_when_perturbed_deferred() -> None:
    """A NOMINAL-only deferred report still states the PERTURBED reproducibility limit."""
    nominal = arm(Condition.NOMINAL, 15, 20)
    report = DualConditionReport.of(DualConditionSet.create(nominal, None, deferred_protocol()))
    assert PERTURBED_REPRODUCIBILITY_LIMIT in report.render()


def test_limit_names_the_seed_does_not_place_objects_caveat() -> None:
    """The limit text carries the specific trade-off-2 caveat, not a generic hedge."""
    assert "시드" in PERTURBED_REPRODUCIBILITY_LIMIT
    assert "정량화할 수 없다" in PERTURBED_REPRODUCIBILITY_LIMIT
