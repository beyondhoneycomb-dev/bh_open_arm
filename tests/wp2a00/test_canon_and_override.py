"""Acceptance ② — the dry-run is refused when the clamp canon is unselected.

The interlock does not re-implement the refusal; it inherits it. A ``DryRunRunner``
cannot be constructed without a selected canon (Wave 0-C ``ClampCanon`` refuses at
construction), and ``run_and_gate`` requires a constructed runner — so the interlock
path cannot even be driven with an unselected canon. This file pins that inheritance
and, alongside it, that the single sanctioned way to arm a *failing* verdict is the
explicit modal override (reused from Wave 0-C), so no other arming path exists.
"""

from __future__ import annotations

import pytest

from backend.interlock import InterlockState, RealSendBarrier
from sim.dryrun.canon import ClampCanon, ClampCanonUnselectedError, PositionCanon, VelocityCanon
from sim.dryrun.interlock import HardBlockError, ModalConfirmation
from sim.dryrun.runner import DryRunRunner
from sim.dryrun.violation import DryRunCheck
from tests.wp2a00._fixtures import real_violations_by_check, verdict_of


def test_unselected_canon_cannot_build_the_dry_run_runner() -> None:
    """FR-SIM-132: with no canon selected the runner (and thus the interlock) refuses."""
    with pytest.raises(ClampCanonUnselectedError):
        DryRunRunner(ClampCanon())


def test_half_selected_canon_is_also_refused() -> None:
    """A canon with only one axis chosen is still unselected — the interlock cannot run."""
    with pytest.raises(ClampCanonUnselectedError):
        DryRunRunner(ClampCanon(position=PositionCanon.MJCF))
    with pytest.raises(ClampCanonUnselectedError):
        DryRunRunner(ClampCanon(velocity=VelocityCanon.OPENARM_CONTROL))


def test_modal_override_is_the_only_path_that_arms_a_failing_verdict() -> None:
    """A failing verdict arms only through the sanctioned modal confirm, never `gate`."""
    violations = real_violations_by_check()[DryRunCheck.CELL_COLLISION]
    verdict = verdict_of(violations)

    barrier = RealSendBarrier()
    assert barrier.gate(verdict).state is InterlockState.BLOCKED

    confirmation = ModalConfirmation(
        operator="op-1", confirmed=True, acknowledged_items=frozenset(verdict.items_hit())
    )
    decision = barrier.override(verdict, confirmation)
    assert decision.state is InterlockState.ARMED
    assert decision.via_modal_confirm is True
    assert barrier.authorize_real_transition().via_modal_confirm is True


def test_modal_override_refuses_a_confirmation_that_misses_a_violation() -> None:
    """An override acknowledging only some violations is refused — no blanket wave-through."""
    violations = real_violations_by_check()[DryRunCheck.CELL_COLLISION]
    verdict = verdict_of(violations)
    empty_ack = ModalConfirmation(operator="op-1", confirmed=True)

    barrier = RealSendBarrier()
    with pytest.raises(HardBlockError):
        barrier.override(verdict, empty_ack)
    assert barrier.permits_real_send is False
