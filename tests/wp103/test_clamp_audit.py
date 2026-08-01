"""Acceptance ⑯ — the `safetyOverride` names the cause that actually stopped the command.

The recorded reason is what somebody reads after an incident, and it is read by code as well:
`backend.eval.taxonomy.engine` derives `POLICY_OUT_OF_BOUNDS` from `ClampReason.JOINT_LIMIT`
alone, and `contracts.errors.integration.code_for_clamp` turns each reason into the OA-* code an
operator sees. So a reason recorded as a joint limit is an assertion that the arm reached the
edge of its travel — and when the truth was a command trying to drive position with zero damping,
the incident reader is looking for a mechanical cause that does not exist while the gain that
Damiao says makes the motor run away goes unmentioned.

The map is total over `SafetyReason` and read without a fallback, because a fallback is what
lets a newly added reason inherit somebody else's meaning silently. An unclassified reason has
to fail where it was introduced.
"""

from __future__ import annotations

from typing import cast

import pytest

from backend.actuation import SafetyReason
from backend.actuation.safety import clamp_reason_for
from contracts.action import ClampReason
from tests.wp103.conftest import degs, make_gateway, make_limits

# A stiffness that plainly drives a position, and the damping that makes the pair the one
# `03` FR-MOT-021 refuses.
DRIVING_KP = 240.0
ZERO_KD = 0.0

# A stiffness past the encoder's 12-bit [0,500] field, and a damping past its [0,5] one.
OVER_RANGE_KP = 600.0
OVER_RANGE_KD = 6.0

# A position past the 90 deg operational limit the narrow fixture envelope carries.
PAST_OPERATIONAL_LIMIT_DEG = 120.0
AT_OPERATIONAL_LIMIT_DEG = 90.0


def test_every_safety_reason_carries_an_explicit_clamp_reason() -> None:
    """Every reason is classified, so a new one cannot ship recorded as something it is not."""
    for reason in SafetyReason:
        assert isinstance(clamp_reason_for(reason), ClampReason)


def test_an_unclassified_reason_fails_rather_than_defaulting() -> None:
    """A reason with no entry raises here instead of being written into the audit as a guess.

    This is the case a fallback erases. With one, an unmapped reason resolves to whatever the
    fallback names and the log reads as certain about a cause nobody classified; the only place
    the omission could then be noticed is an incident review, months later.
    """
    unclassified = cast(SafetyReason, object())

    with pytest.raises(KeyError):
        clamp_reason_for(unclassified)


def test_zero_damping_under_a_driving_stiffness_is_not_recorded_as_a_joint_limit() -> None:
    """The audit says a torque-side refusal, because that is what a gain refusal is."""
    gateway, _guard = make_gateway(make_limits())

    result = gateway.submit(
        degs(1.0, 1.0), degs(0.0, 0.0), kp=(DRIVING_KP, DRIVING_KP), kd=(ZERO_KD, ZERO_KD)
    )

    assert result.reason is SafetyReason.KD_ZERO_POSITION_CONTROL
    assert result.override.clamp_reason is ClampReason.TORQUE_LIMIT
    assert result.override.override_active
    assert not result.override.latched
    assert not result.override.stale


def test_an_over_range_stiffness_is_not_recorded_as_a_joint_limit() -> None:
    """A wrapped-stiffness refusal is on the torque axis; the arm never approached a limit."""
    gateway, _guard = make_gateway(make_limits())

    result = gateway.submit(degs(1.0, 1.0), degs(0.0, 0.0), kp=(OVER_RANGE_KP, DRIVING_KP))

    assert result.reason is SafetyReason.KP_OUT_OF_RANGE
    assert result.override.clamp_reason is ClampReason.TORQUE_LIMIT


def test_an_over_range_damping_is_not_recorded_as_a_joint_limit() -> None:
    """The damping half of the encoder band records the same way its stiffness half does."""
    gateway, _guard = make_gateway(make_limits())

    result = gateway.submit(degs(1.0, 1.0), degs(0.0, 0.0), kd=(OVER_RANGE_KD, 1.0))

    assert result.reason is SafetyReason.KD_OUT_OF_RANGE
    assert result.override.clamp_reason is ClampReason.TORQUE_LIMIT


def test_a_clean_pass_records_no_intervention() -> None:
    """A command nothing touched says so, or every accepted command reads as one safety stopped.

    `override_active` is the field an incident reader counts. Recorded True on a clean pass, the
    whole episode reads as a run the safety layer was fighting, and the commands it genuinely
    altered become indistinguishable from the ones it passed through untouched. The reason field
    cannot substitute: NONE with the flag set is a contradiction nobody reads twice.
    """
    gateway, _guard = make_gateway(make_limits())

    result = gateway.submit(degs(1.0, 1.0), degs(0.0, 0.0))

    assert not result.rejected
    assert result.override.override_active is False
    assert result.override.clamp_reason is ClampReason.NONE
    assert not result.override.stale
    assert not result.override.latched


def test_a_clip_and_proceed_clamp_records_an_intervention() -> None:
    """The other direction of the same field: a command that was altered must not read as clean.

    A clip-and-proceed clamp is admitted, so the flag is the only thing separating it from a
    command that passed as written — the accepted vector alone cannot say whether the caller asked
    for that value or the limit stage supplied it.
    """
    gateway, _guard = make_gateway(make_limits())

    result = gateway.submit(
        degs(PAST_OPERATIONAL_LIMIT_DEG, 0.0), degs(AT_OPERATIONAL_LIMIT_DEG, 0.0)
    )

    assert not result.rejected
    assert result.override.override_active is True


def test_a_genuine_joint_limit_clamp_is_still_recorded_as_one() -> None:
    """The one cause that may claim `JOINT_LIMIT` still does — the taxonomy signal depends on it.

    Separating the gain refusals from this reason is only worth anything if the reason still
    fires where it belongs; a map that stopped emitting it would silence `POLICY_OUT_OF_BOUNDS`
    for every episode instead of merely mistagging some.
    """
    gateway, _guard = make_gateway(make_limits())

    result = gateway.submit(
        degs(PAST_OPERATIONAL_LIMIT_DEG, 0.0), degs(AT_OPERATIONAL_LIMIT_DEG, 0.0)
    )

    assert result.override.clamp_reason is ClampReason.JOINT_LIMIT
    assert result.accepted[0].value == AT_OPERATIONAL_LIMIT_DEG
