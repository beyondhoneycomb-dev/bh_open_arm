"""Acceptance ① (CG-2A-05a) — the original request and the post-clamp action, both recorded.

The ring records `requestedPositionAction` and `acceptedPositionAction` together for
every tick, and when a clamp fires the two genuinely differ. The pair is the Wave-1
`GateFrame`, embedded in the record, so a one-sided frame is unconstructible — the
"both channels, always" rule is reused, not restated. A clean pass records the two
equal; a joint-limit clamp records them different, with the clamp reason.
"""

from __future__ import annotations

from backend.actuation import GateFrame
from backend.audit import AuditRecord, AuditRingBuffer
from contracts.action import ClampReason, validate_frame
from contracts.units import Deg
from tests.wp2a05.conftest import WIDTH, filled, make_gateway, record_from


def _with_joint(base: tuple[Deg, ...], index: int, value: float) -> tuple[Deg, ...]:
    """Return a copy of a degree vector with one joint overridden."""
    joints = list(base)
    joints[index] = Deg(value)
    return tuple(joints)


def test_clamp_records_request_and_accepted_and_they_differ() -> None:
    """A joint-limit clamp records both channels, and the recorded pair differs (①)."""
    gateway, _guard = make_gateway()
    ring = AuditRingBuffer()

    # Joint 0 is commanded past the 90 deg operational limit while the arm sits at the
    # limit, so the clamp is the only decisive check and the accepted angle is 90, not 120.
    request = _with_joint(filled(0.0), 0, 120.0)
    present = _with_joint(filled(0.0), 0, 90.0)
    result = gateway.submit(request, present)

    ring.record(record_from(result, request, tick_index=0, at=0.0))
    entry = ring.records[-1]

    assert len(entry.requested) == WIDTH
    assert len(entry.accepted) == WIDTH
    assert entry.requested[0] == Deg(120.0)
    assert entry.accepted[0] == Deg(90.0)
    assert entry.clamped
    assert entry.clamp_reason is ClampReason.JOINT_LIMIT
    assert entry.override.override_active


def test_clean_pass_records_both_channels_equal() -> None:
    """With no clamp, request and accepted are both recorded and equal, reason NONE (①)."""
    gateway, _guard = make_gateway()
    ring = AuditRingBuffer()

    request = filled(10.0)
    result = gateway.submit(request, filled(10.0))

    ring.record(record_from(result, request, tick_index=0, at=0.0))
    entry = ring.records[-1]

    assert entry.requested == entry.accepted
    assert not entry.clamped
    assert entry.clamp_reason is ClampReason.NONE


def test_recorded_pair_satisfies_the_ctr_act_both_channels_rule() -> None:
    """The recorded frame is the Wave-1 pair; the CTR-ACT both-channels rule holds (①)."""
    gateway, _guard = make_gateway()
    ring = AuditRingBuffer()
    request = filled(5.0)
    result = gateway.submit(request, filled(5.0))

    ring.record(record_from(result, request, tick_index=0, at=0.0))
    entry = ring.records[-1]

    assert isinstance(entry.frame, GateFrame)
    # The contract's own rule agrees: both channels present is the only accepted shape.
    assert validate_frame(has_requested=True, has_accepted=True) == ()
    # And a post-clamp-only frame is exactly what the contract refuses.
    assert validate_frame(has_requested=False, has_accepted=True) != ()


def test_a_one_sided_record_is_unconstructible() -> None:
    """Building an AuditRecord requires a two-channel GateFrame — no one-sided path (①)."""
    # GateFrame takes both channels as mandatory fields; there is no constructor that
    # yields a request-only or accepted-only frame, so the recording rule cannot lapse.
    frame_fields = set(GateFrame.__dataclass_fields__)
    assert frame_fields == {"requested", "accepted"}
    assert "frame" in AuditRecord.__dataclass_fields__
