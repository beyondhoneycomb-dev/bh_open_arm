"""The event ring reuses the WP-2A-05 audit ring — one event, one coherent dump.

WP-2C-09 must not stand up a second ring buffer beside the audit one. Bound to a real
`AuditRingBuffer` filled through the genuine Wave-1 gateway, a single `on_safety_event`
snapshots both: the returned event dump carries the audit command/decision window
beside the physical-telemetry window, under the same `LatchReason` and timestamp. This
is the reuse the plan calls for (`02b` §3 WP-2C-09 input = WP-2A-05 ring), proven by the
two windows sharing one trigger rather than by inspecting the ring's internals.
"""

from __future__ import annotations

from backend.audit import AuditRingBuffer
from backend.event_ring import EventRingBuffer
from ops.cancel.scheduler import LatchReason
from tests.wp2a05.conftest import filled, make_gateway, record_from
from tests.wp2c09.conftest import DT_SEC, encoded_sample

_PRE_SEC = 2.0
_POST_SEC = 2.0
_EVENT_TICK = 250
_EVENT_AT = _EVENT_TICK * DT_SEC


def _fill_audit(audit: AuditRingBuffer, ticks: int) -> None:
    """Record `ticks` real clamped decisions into the audit ring via the Wave-1 gateway."""
    gateway, _guard = make_gateway()
    request = filled(120.0)  # beyond the 90° operational bound, so the clamp genuinely fires
    for index in range(ticks):
        result = gateway.submit(request, filled(120.0))
        audit.record(record_from(result, request, tick_index=index, at=index * DT_SEC))


def _bound_rings() -> tuple[EventRingBuffer, AuditRingBuffer]:
    """An event ring bound to an audit ring, both filled and ready to arm at the event."""
    audit = AuditRingBuffer()
    _fill_audit(audit, ticks=_EVENT_TICK + 1)
    ring = EventRingBuffer(
        capacity=int(_PRE_SEC * 100) + 100,
        pre_event_sec=_PRE_SEC,
        post_event_sec=_POST_SEC,
        audit_ring=audit,
    )
    for tick in range(_EVENT_TICK + 1):
        ring.record(encoded_sample(tick))
    return ring, audit


def test_one_event_dumps_both_windows() -> None:
    """A single safe-stop yields telemetry and the paired audit window in one dump."""
    ring, _audit = _bound_rings()
    reason = LatchReason("COLLISION_GUARD:collision_residual", "PASS", "LATCHED", _EVENT_AT)

    capture = ring.on_safety_event(reason)
    tick = _EVENT_TICK + 1
    while not capture.complete:
        ring.record(encoded_sample(tick))
        tick += 1
    dump = capture.dump

    # Physical telemetry present…
    assert len(dump.pre) > 0
    assert len(dump.post) > 0
    # …and the audit command/decision window came along under the same trigger.
    assert dump.audit is not None
    assert len(dump.audit.records) > 0
    assert dump.audit.trigger is reason
    assert dump.audit.dumped_at == _EVENT_AT
    # The clamp genuinely fired in the audit window: request and accepted differ.
    assert any(record.clamped for record in dump.audit.records)


def test_unbound_ring_dumps_telemetry_only() -> None:
    """Without an audit ring the dump still stands, carrying a None audit peer."""
    ring = EventRingBuffer(capacity=400, pre_event_sec=_PRE_SEC, post_event_sec=_POST_SEC)
    for tick in range(_EVENT_TICK + 1):
        ring.record(encoded_sample(tick))
    capture = ring.on_safety_event(LatchReason("g", "PASS", "LATCHED", _EVENT_AT))
    tick = _EVENT_TICK + 1
    while not capture.complete:
        ring.record(encoded_sample(tick))
        tick += 1

    assert capture.dump.audit is None
    assert len(capture.dump.pre) > 0
