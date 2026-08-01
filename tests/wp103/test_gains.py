"""Acceptance ⑦ — kp/kd validated then rejected, never silently wrapped (`03` FR-MOT-018).

The CAN packet carries kp in a 12-bit field scaled to [0,500] and kd to [0,5]; an
over-range gain is silently wrapped by the encoder into a different, unrequested
stiffness that would run anyway. So a gain outside its range is rejected at the
gateway before it can reach the wire, with its own distinct reason.

The encoder bound is not the only bound on kd. `03` FR-MOT-021 and `04` FR-MAN-031 forbid
one *pair*: a non-zero stiffness with zero damping. It encodes perfectly, so no range check
can see it, and Damiao states what the motor does with it — "When controlling the position,
kd cannot be set to 0. Otherwise it will cause the motor vibrate or go out of control."
The pair with kp=0 is the opposite case and stays admissible: that is the Freedrive/pure
feed-forward frame `04` §2.8 names, and refusing it would forbid a documented mode.
"""

from __future__ import annotations

from backend.actuation import SafetyReason
from backend.actuation.config import MIT_HOLD_KD, MIT_HOLD_KP
from tests.wp103.conftest import degs, make_gateway, make_limits

# A stiffness that plainly drives a position, well inside [0,500].
DRIVING_KP = 240.0

# The damping the forbidden pair carries.
ZERO_KD = 0.0

# A damping that is small but non-zero — the Freedrive band's default (`04` FR-MAN-030).
SMALL_KD = 0.2

# Gains below the floor of their band. The band has two ends and the lower one is the worse
# failure: the MIT law is `tau = kp*(q_cmd - q) + kd*(dq_cmd - dq) + tau_ff`, so a negative kp
# pushes the joint away from the angle it was told to hold, and harder the further it gets, while
# a negative kd adds energy to whatever the joint is already doing instead of taking it out. On an
# arm with no mechanical brake neither is a wrong pose, both are a runaway, and Damiao's note
# about kd=0 is the milder end of the same behaviour.
NEGATIVE_KP = -100.0
NEGATIVE_KD = -1.0

# The stiffness that makes zero-or-below damping legal: at kp=0 the MIT law carries no position
# term, so the negative-damping case is judged by the encoder band alone and nothing else can
# stand in for it (`04` §2.8).
NO_KP = 0.0


def test_kp_above_500_is_rejected() -> None:
    """A stiffness above 500 is rejected, not wrapped (⑦)."""
    gateway, _guard = make_gateway(make_limits())
    result = gateway.submit(degs(1.0, 1.0), degs(0.0, 0.0), kp=(600.0, 100.0))
    assert result.rejected
    assert result.reason is SafetyReason.KP_OUT_OF_RANGE


def test_kd_above_5_is_rejected() -> None:
    """A damping above 5 is rejected, not wrapped (⑦)."""
    gateway, _guard = make_gateway(make_limits())
    result = gateway.submit(degs(1.0, 1.0), degs(0.0, 0.0), kd=(6.0, 1.0))
    assert result.rejected
    assert result.reason is SafetyReason.KD_OUT_OF_RANGE


def test_a_negative_stiffness_is_rejected() -> None:
    """A stiffness below the band inverts the position loop and is refused before the wire.

    The other joint carries a driving stiffness with real damping, so the only thing wrong with
    this command is the sign on joint 0 — a case that refused it for the pair instead would pass
    with the sign check gone.
    """
    gateway, _guard = make_gateway(make_limits())
    result = gateway.submit(
        degs(1.0, 1.0), degs(0.0, 0.0), kp=(NEGATIVE_KP, DRIVING_KP), kd=(SMALL_KD, SMALL_KD)
    )
    assert result.rejected
    assert result.reason is SafetyReason.KP_OUT_OF_RANGE


def test_a_negative_damping_is_rejected() -> None:
    """A damping below the band drives the joint with positive velocity feedback, so it is refused.

    The stiffness is zero here on purpose. Under a driving stiffness the FR-MOT-021 damping floor
    would refuse this command anyway and stand in for the band check; at kp=0 there is no position
    term and the encoder band is the only thing between a negative kd and the motor.
    """
    gateway, _guard = make_gateway(make_limits())
    result = gateway.submit(
        degs(1.0, 1.0), degs(0.0, 0.0), kp=(NO_KP, NO_KP), kd=(NEGATIVE_KD, NEGATIVE_KD)
    )
    assert result.rejected
    assert result.reason is SafetyReason.KD_OUT_OF_RANGE


def test_in_range_gains_are_accepted() -> None:
    """Gains inside their ranges pass the gain check (⑦, no over-eager reject)."""
    gateway, _guard = make_gateway(make_limits())
    result = gateway.submit(degs(1.0, 1.0), degs(0.0, 0.0), kp=(240.0, 240.0), kd=(5.0, 3.0))
    assert not result.rejected
    assert result.reason is SafetyReason.NONE


def test_boundary_gains_are_accepted() -> None:
    """The inclusive bounds (0 and the max) are in range (⑦)."""
    gateway, _guard = make_gateway(make_limits())
    result = gateway.submit(degs(1.0, 1.0), degs(0.0, 0.0), kp=(0.0, 500.0), kd=(0.0, 5.0))
    assert not result.rejected


def test_zero_damping_under_a_driving_stiffness_is_rejected() -> None:
    """The pair Damiao says makes the motor run away is refused (`03` FR-MOT-021)."""
    gateway, _guard = make_gateway(make_limits())
    result = gateway.submit(
        degs(1.0, 1.0), degs(0.0, 0.0), kp=(DRIVING_KP, DRIVING_KP), kd=(ZERO_KD, SMALL_KD)
    )
    assert result.rejected
    assert result.reason is SafetyReason.KD_ZERO_POSITION_CONTROL


def test_zero_damping_with_no_stiffness_is_admitted() -> None:
    """kp=0 is not position control, so kd=0 there is the pure-torque frame, not a runaway.

    `04` §2.8 quotes Damiao: "When kp=0 and kd=0, a given t_ff will achieve a given torque
    output." Refusing this pair would forbid gravity-compensated Freedrive outright.
    """
    gateway, _guard = make_gateway(make_limits())
    result = gateway.submit(degs(1.0, 1.0), degs(0.0, 0.0), kp=(0.0, 0.0), kd=(ZERO_KD, ZERO_KD))
    assert not result.rejected


def test_omitting_the_stiffness_does_not_excuse_zero_damping() -> None:
    """An unnamed kp is the hold stiffness, which drives a position — so kd=0 is still refused.

    `positions_to_batch` writes `MIT_HOLD_KP` into every slot the caller left unnamed, so a
    command that names only kd is a position command whether or not it said so.
    """
    gateway, _guard = make_gateway(make_limits())
    result = gateway.submit(degs(1.0, 1.0), degs(0.0, 0.0), kd=(ZERO_KD, ZERO_KD))
    assert result.rejected
    assert result.reason is SafetyReason.KD_ZERO_POSITION_CONTROL


def test_a_stiffness_named_without_a_damping_is_admitted_on_the_hold_damping() -> None:
    """Retuning stiffness alone is a normal command, and the damping it is paired with is the hold.

    The unnamed slot is not empty on the wire: `positions_to_batch` writes `MIT_HOLD_KD` into it,
    so the pair judged here is the pair the joint is actually sent. Filling it with zero instead
    would refuse every command that names a stiffness and leaves damping alone — which is what
    tuning a joint's stiffness looks like — and nothing else in this file would notice, because
    nothing else supplies kp without kd.
    """
    gateway, _guard = make_gateway(make_limits())
    result = gateway.submit(degs(1.0, 1.0), degs(0.0, 0.0), kp=(DRIVING_KP, DRIVING_KP))
    assert not result.rejected
    assert result.reason is SafetyReason.NONE


def test_the_hold_damping_is_admitted() -> None:
    """The gains the spine actually holds with must survive the rule, or nothing can hold."""
    gateway, _guard = make_gateway(make_limits())
    result = gateway.submit(
        degs(1.0, 1.0),
        degs(0.0, 0.0),
        kp=(MIT_HOLD_KP, MIT_HOLD_KP),
        kd=(MIT_HOLD_KD, MIT_HOLD_KD),
    )
    assert not result.rejected
    assert result.reason is SafetyReason.NONE
