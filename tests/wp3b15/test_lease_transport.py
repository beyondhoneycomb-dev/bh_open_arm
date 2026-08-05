"""The lease round trip: the WS carries the deadman's verdict and decides none of it.

Every assertion here is about transport. The decisions — accept, refuse, which of the six
refusal reasons, what the expiry is — belong to `backend.deadman`, and these tests check
that what came back on the wire is what the canon decided, not that the WS decided the
same thing. So the refusals are provoked through the canon's own rules (a replayed
sequence, a latch) rather than by feeding the server something it would refuse locally.

The expiry on a granted lease is asserted against the `DEADMAN_LEASE_DURATION_SEC` the
canon computes from the *server* clock, which is the property `CTR-WS@v2` acceptance ⑤
turns on: a client sends no expiry field at all, so the number that comes back cannot
have come from it.
"""

from __future__ import annotations

import pytest

from backend.deadman import DEADMAN_LEASE_DURATION_SEC, RenewalDecision
from backend.ws import ENVELOPE_TYPE_FIELD, WS_CLOSE_REARM_NOT_ISSUED
from contracts.prim import LEASE_EXPIRY_FIELD, LEASE_ISSUED_FIELD
from contracts.ws import (
    LEASE_GENERATION_FIELD,
    LEASE_REASON_FIELD,
    LEASE_SEQUENCE_FIELD,
    LEASE_SESSION_FIELD,
    LeaseRejectReason,
    WsFrameType,
    WsRole,
)
from tests.wp3b15.conftest import (
    DEFAULT_SESSION_ID,
    WsFixture,
    connect,
    expect_close,
    frame,
    renew_frame,
    stop_frame,
    take_deadman,
)


def test_accepted_renewal_comes_back_as_a_grant_with_a_server_authored_expiry(
    ws: WsFixture,
) -> None:
    """The first renewal of the live generation is granted, and the expiry is the server's."""
    ws.clock.advance(2.0)
    with connect(ws, WsRole.OPERATOR) as socket:
        socket.send_json(
            renew_frame(generation=ws.deadman.current_generation, sequence=1, issued=2.0)
        )
        reply = socket.receive_json()

    assert reply[ENVELOPE_TYPE_FIELD] == WsFrameType.LEASE_GRANT.value
    assert reply[LEASE_SESSION_FIELD] == DEFAULT_SESSION_ID
    assert reply[LEASE_GENERATION_FIELD] == 0
    assert reply[LEASE_SEQUENCE_FIELD] == 1
    assert reply[LEASE_ISSUED_FIELD] == 2.0
    assert reply[LEASE_EXPIRY_FIELD] == pytest.approx(2.0 + DEADMAN_LEASE_DURATION_SEC)


def test_replayed_sequence_comes_back_as_the_canon_reject_reason(ws: WsFixture) -> None:
    """A replay is refused by the canon and reaches the client as `rejected_replay` (③)."""
    take_deadman(ws, sequence=5)
    with connect(ws, WsRole.OPERATOR) as socket:
        # Sequence 5 was already accepted, so this is a replay by the receiver's rule.
        socket.send_json(
            renew_frame(generation=ws.deadman.current_generation, sequence=5, issued=0.0)
        )
        reply = socket.receive_json()

    assert reply[ENVELOPE_TYPE_FIELD] == WsFrameType.LEASE_REJECT.value
    assert reply[LEASE_REASON_FIELD] == LeaseRejectReason.REJECTED_REPLAY.value
    assert reply[LEASE_REASON_FIELD] == RenewalDecision.REJECTED_REPLAY.value


def test_a_stop_latches_the_lease_and_the_next_renewal_says_so(ws: WsFixture) -> None:
    """The GUI stop and the lease share one latch, and the wire reason proves it (⑤)."""
    take_deadman(ws)
    with connect(ws, WsRole.OBSERVER) as socket:
        socket.send_json(stop_frame())

    with connect(ws, WsRole.OPERATOR) as socket:
        socket.send_json(
            renew_frame(generation=ws.deadman.current_generation, sequence=2, issued=0.0)
        )
        reply = socket.receive_json()

    assert reply[ENVELOPE_TYPE_FIELD] == WsFrameType.LEASE_REJECT.value
    assert reply[LEASE_REASON_FIELD] == LeaseRejectReason.REJECTED_LATCHED.value


def test_rearm_confirm_clears_the_latch_and_returns_the_new_generation(
    ws: WsFixture,
) -> None:
    """The operator half of the handshake is the only path back to live (④)."""
    take_deadman(ws)
    with connect(ws, WsRole.OBSERVER) as socket:
        socket.send_json(stop_frame())
    assert ws.latch.is_active

    # The server issues the generation; `rearm_issue` is a server-to-client frame, so it
    # is not something a client sends and not something this route accepts.
    issued = ws.deadman.request_rearm()

    with connect(ws, WsRole.OPERATOR) as socket:
        socket.send_json(
            frame(
                WsFrameType.REARM_CONFIRM,
                **{LEASE_SESSION_FIELD: DEFAULT_SESSION_ID, LEASE_GENERATION_FIELD: issued},
            )
        )
        reply = socket.receive_json()

    assert reply[ENVELOPE_TYPE_FIELD] == WsFrameType.REARM_ACCEPT.value
    assert reply[LEASE_GENERATION_FIELD] == issued
    assert ws.deadman.current_generation == issued
    assert not ws.latch.is_active
    # No lease has been granted under the new generation yet, so the server has computed
    # no expiry and states none. The next `lease_renew` is what carries a real one.
    assert reply[LEASE_EXPIRY_FIELD] is None
    assert reply[LEASE_SEQUENCE_FIELD] is None
    assert reply[LEASE_ISSUED_FIELD] is None


def test_rearm_confirm_with_nothing_issued_is_refused(ws: WsFixture) -> None:
    """A confirmation answering no offer resumes nothing, and the client is told why."""
    take_deadman(ws)
    with connect(ws, WsRole.OBSERVER) as socket:
        socket.send_json(stop_frame())

    with connect(ws, WsRole.OPERATOR) as socket:
        socket.send_json(
            frame(
                WsFrameType.REARM_CONFIRM,
                **{LEASE_SESSION_FIELD: DEFAULT_SESSION_ID, LEASE_GENERATION_FIELD: 1},
            )
        )
        refusal = expect_close(socket)

    assert refusal.code == WS_CLOSE_REARM_NOT_ISSUED
    assert ws.latch.is_active


def test_observer_may_not_renew_or_confirm(ws: WsFixture) -> None:
    """Both lease frames a client authors are control frames; an observer holds neither (⑥)."""
    for payload in (
        renew_frame(generation=0, sequence=1, issued=0.0),
        frame(
            WsFrameType.REARM_CONFIRM,
            **{LEASE_SESSION_FIELD: DEFAULT_SESSION_ID, LEASE_GENERATION_FIELD: 1},
        ),
    ):
        with connect(ws, WsRole.OBSERVER) as socket:
            socket.send_json(payload)
            expect_close(socket)
