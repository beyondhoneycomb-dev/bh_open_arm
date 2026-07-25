"""CG-5-08c — forced release fences the prior holder, HOLD before release (FR-OPS-076/091).

A forced release must (a) transition to a safe HOLD *before* it releases the lock, and
(b) increment the one lease's generation so the prior holder's resent commands are
refused for a stale generation. Both are checked here against the real deadman lease
and the real command guard.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from backend.security.command_lease import CommandDecision, CommandEnvelope, CommandGuard
from backend.security.control_lock import CommandSource, CommandSourceLock
from backend.security.forced_release import (
    ForcedRelease,
    ForcedReleaseError,
    ForceReleaseStep,
)
from contracts.ws import WsRole
from tests.wp5_08._support import DeadmanFixture, build_deadman, latch_reason, take_deadman

_PRIOR = "prior-operator"


@dataclass(frozen=True)
class Control:
    """A live control setup: the guard, the L2 lock, the forced release, and the lease."""

    guard: CommandGuard
    lock: CommandSourceLock
    forced: ForcedRelease
    generation: int
    fixture: DeadmanFixture


def _live_control() -> Control:
    fixture = build_deadman()
    take_deadman(fixture)
    lock = CommandSourceLock(fixture.clock)
    assert lock.acquire(_PRIOR, CommandSource.VR, WsRole.OPERATOR).granted
    guard = CommandGuard(fixture.controller, fixture.lease, lock, fixture.clock)
    forced = ForcedRelease(fixture.controller, fixture.latch, lock)
    return Control(guard, lock, forced, fixture.controller.current_generation, fixture)


def test_hold_is_engaged_before_the_lock_is_released() -> None:
    control = _live_control()

    outcome = control.forced.execute(WsRole.ADMIN, latch_reason(control.fixture.clock.now()))

    hold_index = outcome.steps.index(ForceReleaseStep.HOLD_ENGAGED)
    release_index = outcome.steps.index(ForceReleaseStep.LOCK_RELEASED)
    assert hold_index < release_index
    assert outcome.held_before_release is True
    assert outcome.latched_after is True


def test_generation_increments_and_lock_is_released() -> None:
    control = _live_control()

    outcome = control.forced.execute(WsRole.ADMIN, latch_reason(control.fixture.clock.now()))

    assert outcome.previous_generation == control.generation
    assert outcome.new_generation == control.generation + 1
    assert control.lock.holder is None


def test_prior_holder_resent_command_is_refused_on_generation_mismatch() -> None:
    control = _live_control()
    # The prior holder had a live, accepted command stream before the release.
    assert control.guard.validate(
        CommandEnvelope(_PRIOR, control.generation, sequence=1, timestamp_mono_client=1.0),
        WsRole.OPERATOR,
    ).accepted

    control.forced.execute(WsRole.ADMIN, latch_reason(control.fixture.clock.now()))

    # A captured command from before the release, resent, still carries the old
    # generation — the fence refuses it for a generation mismatch, not merely because
    # the lock has moved.
    resent = CommandEnvelope(_PRIOR, control.generation, sequence=2, timestamp_mono_client=2.0)
    verdict = control.guard.validate(resent, WsRole.OPERATOR)
    assert verdict.decision is CommandDecision.REFUSED_GENERATION_MISMATCH


def test_non_admin_cannot_force_release() -> None:
    control = _live_control()

    for role in (WsRole.OPERATOR, WsRole.OBSERVER):
        with pytest.raises(ForcedReleaseError):
            control.forced.execute(role, latch_reason(control.fixture.clock.now()))

    # The lock is untouched by a refused release attempt.
    assert control.lock.holder is not None
