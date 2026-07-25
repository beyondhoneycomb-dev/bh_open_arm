"""CG-4C-05c — axes reference the Wave 3C distribution; deferral states 'gap unmeasured'.

`02c` §3.5: perturbation axes are not invented by the plan — each is derived from the
Wave 3C initial-state distribution, so an axis with no distribution reference is refused
(the "0 arbitrary axes" guarantee). Because that distribution has not landed, the only
protocol this phase produces is the deferred one, and its report states the exact
"일반화 격차 미측정" phrase and names the missing Wave 3C distribution — a deferral, not a
FAIL (`02c` §3.5 ③ negative branch).
"""

from __future__ import annotations

from backend.eval.protocol import (
    Condition,
    DualConditionReport,
    DualConditionSet,
    PerturbationAxis,
    PerturbationError,
    PerturbationProtocol,
)
from backend.eval.protocol.constants import (
    GENERALIZATION_GAP_UNMEASURED,
    WAVE_3C_DISTRIBUTION_REF,
)
from tests.wp4c05.support import arm, axis, deferred_protocol


def test_axis_without_distribution_reference_is_refused() -> None:
    """An axis that references no source distribution is an arbitrary axis -> refused."""
    try:
        PerturbationAxis(name="object_x_position", distribution_ref="   ")
    except PerturbationError as error:
        assert "reference" in str(error).lower()
        return
    raise AssertionError("an axis with no distribution reference must be refused (CG-4C-05c)")


def test_defined_axis_carries_a_distribution_reference() -> None:
    """A well-formed axis carries a non-empty Wave 3C distribution reference."""
    defined = axis()
    assert defined.distribution_ref.strip()
    assert WAVE_3C_DISTRIBUTION_REF in defined.distribution_ref


def test_deferred_protocol_references_wave_3c_and_has_no_axes() -> None:
    """The deferred protocol names the missing Wave 3C distribution and defines no axes."""
    protocol = deferred_protocol("pick")
    assert protocol.is_deferred is True
    assert protocol.axes == ()
    assert WAVE_3C_DISTRIBUTION_REF in protocol.deferred_reason
    assert GENERALIZATION_GAP_UNMEASURED in protocol.deferred_reason


def test_deferred_protocol_cannot_carry_axes() -> None:
    """A deferred protocol carrying axes is a contradiction and is refused."""
    try:
        PerturbationProtocol(task_id="pick", axes=(axis(),), deferred_reason="deferred")
    except PerturbationError:
        return
    raise AssertionError("a deferred protocol must carry no axes")


def test_defined_protocol_needs_at_least_one_axis() -> None:
    """A defined (non-deferred) protocol with no axes perturbs nothing and is refused."""
    try:
        PerturbationProtocol(task_id="pick", axes=(), deferred_reason="")
    except PerturbationError:
        return
    raise AssertionError("a defined protocol must carry at least one axis")


def test_nominal_only_report_states_gap_unmeasured() -> None:
    """NOMINAL-only proceeds; the report states '일반화 격차 미측정' and names Wave 3C."""
    nominal = arm(Condition.NOMINAL, 15, 20)
    dual = DualConditionSet.create(nominal, None, deferred_protocol("pick"))
    report = DualConditionReport.of(dual)

    assert report.gap_measured is False
    assert report.generalization_gap is None
    rendered = report.render()
    assert GENERALIZATION_GAP_UNMEASURED in rendered
    assert WAVE_3C_DISTRIBUTION_REF in rendered
