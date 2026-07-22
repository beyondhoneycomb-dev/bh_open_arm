"""The negative branch: every failure blocks, never warns; and no check can be dropped.

WP-2A-09's negative branch is that *any* precondition implemented as "warn then proceed"
is FAIL_BLOCKING. Two structural properties make that unrepresentable, and this test
pins both: a single failed check forces `may_enable_torque` false and `authorize_torque_on`
to raise (no warn-and-continue path exists), and a report cannot even be built unless it
accounts for every precondition (no check can be silently skipped). The all-pass case
confirms the gate is not vacuously blocking.
"""

from __future__ import annotations

import dataclasses

import pytest

from backend.can.lock import LockState
from backend.preflight import (
    PreflightReport,
    RidCrosscheck,
    TorqueOnBlockedError,
    authorize_torque_on,
    check_side,
)
from backend.preflight.preflight import JogSessionPreflight, PreflightInputs
from tests.wp2a09.builders import link_fd_off, passing_inputs


def _single_failure_variants(base: PreflightInputs) -> list[PreflightInputs]:
    """One inputs object per precondition, each with exactly that precondition broken."""
    return [
        dataclasses.replace(base, rid=RidCrosscheck.unavailable("deferred")),
        dataclasses.replace(base, side=None),
        dataclasses.replace(base, link=link_fd_off()),
        dataclasses.replace(base, lock_state=_unheld(base.lock_state)),
        dataclasses.replace(base, clamp_canon=None),
    ]


def _unheld(state: LockState) -> LockState:
    """Return the same lock state as if this process did not hold it."""
    return dataclasses.replace(state, held_by_self=False, holder=None)


def test_all_preconditions_pass_permits_torque(self_held_lock_state: LockState) -> None:
    report = JogSessionPreflight().run(passing_inputs(self_held_lock_state))
    assert report.may_enable_torque
    authorize_torque_on(report)  # does not raise


def test_each_single_failure_blocks_torque(self_held_lock_state: LockState) -> None:
    base = passing_inputs(self_held_lock_state)
    for variant in _single_failure_variants(base):
        report = JogSessionPreflight().run(variant)
        assert not report.may_enable_torque
        assert len(report.failures()) == 1
        with pytest.raises(TorqueOnBlockedError):
            authorize_torque_on(report)


def test_report_rejects_a_dropped_check() -> None:
    # A report that omits a precondition cannot be constructed — the guarantee that no
    # check is silently skipped is structural, not a matter of discipline.
    with pytest.raises(ValueError):
        PreflightReport(results=(check_side(None),))


def test_blocking_summary_names_failures(self_held_lock_state: LockState) -> None:
    inputs = dataclasses.replace(passing_inputs(self_held_lock_state), side=None)
    report = JogSessionPreflight().run(inputs)
    summary = report.blocking_summary()
    assert "side_specified" in summary
