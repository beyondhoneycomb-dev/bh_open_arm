"""SPINE §6 — `executedMitCommand` is audit-only; the training target reads only position.

The action contract keeps safety/gravity torque on a separate execution+audit channel
(`executedMitCommand`, kp/kd/q/dq/tau) that must NOT mix into the training target. This
asserts the dual record's `training_target` returns the position-only accepted action
and cannot reach the audit MIT command — so a training path reading the target never
sees the torque.
"""

from __future__ import annotations

from backend.inference.runaway import DualActionRecorder
from contracts.action import (
    BIMANUAL_ACTION_DIM,
    AcceptedPositionAction,
    ExecutedMitCommand,
    RequestedPositionAction,
)
from contracts.units import Deg, Nm, Rad, RadPerSec


def _audit_batch(tau: float) -> tuple[ExecutedMitCommand, ...]:
    """Build a full audit MIT batch carrying a non-zero feed-forward torque."""
    return tuple(
        ExecutedMitCommand(kp=1.0, kd=1.0, q=Rad(0.0), dq=RadPerSec(0.0), tau=Nm(tau))
        for _ in range(BIMANUAL_ACTION_DIM)
    )


def test_training_target_is_position_only_and_never_the_audit_command() -> None:
    """The training target is the accepted position action; the torque stays audit-only."""
    recorder = DualActionRecorder()
    requested = RequestedPositionAction(values=tuple(Deg(1.0) for _ in range(BIMANUAL_ACTION_DIM)))
    record = recorder.record(requested, joint_limits=None, executed_mit=_audit_batch(7.0))

    target = record.training_target()
    assert isinstance(target, AcceptedPositionAction)
    assert target is record.accepted
    # Position-only: every training-target value is a degree angle, never a torque.
    assert all(isinstance(value, Deg) for value in target.values)
    assert not hasattr(target, "tau")

    # The torque lives on the separate audit channel, recoverable but not in the target.
    assert record.executed_mit is not None
    assert record.executed_mit[0].tau == Nm(7.0)


def test_audit_channel_is_optional_and_defaults_absent() -> None:
    """A record without an attached emission has no audit command — never a training input."""
    recorder = DualActionRecorder()
    requested = RequestedPositionAction(values=tuple(Deg(0.0) for _ in range(BIMANUAL_ACTION_DIM)))
    record = recorder.record(requested, joint_limits=None)

    assert record.executed_mit is None
    assert record.training_target() == record.accepted
