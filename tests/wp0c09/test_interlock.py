"""Acceptance ③/④ — the hard block, and that it has zero implicit bypasses."""

from __future__ import annotations

import pytest

from sim.dryrun.interlock import (
    HardBlockError,
    ModalConfirmation,
    TransmissionGrant,
    authorize_transmission,
    authorize_with_modal_confirm,
)
from sim.dryrun.violation import DryRunCheck, DryRunVerdict, Violation


def _failing_verdict() -> DryRunVerdict:
    return DryRunVerdict(
        violations=(
            Violation(DryRunCheck.POSITION_LIMIT, 0.1, "left_joint_1", 0.2),
            Violation(DryRunCheck.CELL_COLLISION, 0.2, "cell<->link5", 0.03),
        )
    )


def _passing_verdict() -> DryRunVerdict:
    return DryRunVerdict(violations=(), asset_digest="abc", backend="mujoco")


def test_passing_verdict_is_authorized() -> None:
    """A clean verdict authorizes transmission without a modal confirm."""
    grant = authorize_transmission(_passing_verdict())
    assert isinstance(grant, TransmissionGrant)
    assert grant.via_modal_confirm is False


def test_failing_verdict_hard_blocks() -> None:
    """③ Any violation hard-blocks transmission on the plain path."""
    with pytest.raises(HardBlockError):
        authorize_transmission(_failing_verdict())


def test_full_modal_confirm_bypasses_the_block() -> None:
    """The one sanctioned bypass grants when it acknowledges every violated item."""
    verdict = _failing_verdict()
    confirmation = ModalConfirmation(
        operator="op-1",
        confirmed=True,
        acknowledged_items=frozenset(verdict.items_hit()),
    )
    grant = authorize_with_modal_confirm(verdict, confirmation)
    assert grant.via_modal_confirm is True
    assert grant.operator == "op-1"


def test_no_bypass_attempt_succeeds_without_full_explicit_confirm() -> None:
    """③/④ Every under-specified bypass is refused — zero bypass successes."""
    verdict = _failing_verdict()
    all_items = frozenset(verdict.items_hit())
    partial = frozenset({DryRunCheck.POSITION_LIMIT})
    bad_confirmations = [
        ModalConfirmation(operator="op", confirmed=False, acknowledged_items=all_items),
        ModalConfirmation(operator="", confirmed=True, acknowledged_items=all_items),
        ModalConfirmation(operator="op", confirmed=True, acknowledged_items=partial),
        ModalConfirmation(operator="op", confirmed=True, acknowledged_items=frozenset()),
    ]
    successes = 0
    for confirmation in bad_confirmations:
        try:
            authorize_with_modal_confirm(verdict, confirmation)
            successes += 1
        except HardBlockError:
            pass
    assert successes == 0


def test_grant_cannot_be_fabricated_without_the_interlock_key() -> None:
    """④ A TransmissionGrant cannot be minted outside the interlock's authorizers."""
    with pytest.raises(RuntimeError):
        TransmissionGrant(object(), _passing_verdict(), via_modal_confirm=True, operator="x")


def test_modal_confirm_on_a_passing_verdict_is_harmless() -> None:
    """A confirm against a passing verdict still grants (nothing to acknowledge)."""
    confirmation = ModalConfirmation(operator="op", confirmed=True)
    grant = authorize_with_modal_confirm(_passing_verdict(), confirmation)
    assert grant.via_modal_confirm is True
