"""WP-3A-04 — the control lease is TRANSPORTED, not redefined (WP-2A-02 canon, U-4).

This is the contract join `06` §5.6 describes: the `contracts` tree and the
`backend/deadman` tree do not import each other, so the WS transport agreeing with
the dead-man canon is not a static fact — it is proven here, by a test that imports
both and checks the wire against the canon. The agreement, offset by
`CONTRACT_FROZEN` + CI-09, is what makes "transports, does not redefine" real rather
than aspirational.

`02b` §5.2 WP-3A-04 acceptance ③④⑤ live here: expiry/regression/replay/age are the
canon's refusals, transported by value; a post-expiry resume takes the re-arm
handshake, not a renewal; and the client clock never judges expiry, because a
client-authored frame carries no expiry field at all.
"""

from __future__ import annotations

import dataclasses

import pytest

import contracts.ws as ws
from backend.deadman.messages import DeadmanLease, LeaseRenewal, RenewalDecision
from backend.deadman.rearm import RearmHandshake
from contracts.prim import (
    LEASE_EXPIRY_FIELD,
    LEASE_ISSUED_FIELD,
    ClockRole,
    PrimitiveRedefinitionError,
)


def _canon_fields(datatype: type) -> set[str]:
    """Return the field names of a dead-man canon dataclass."""
    return {field.name for field in dataclasses.fields(datatype)}


def test_grant_frame_carries_the_canon_lease_fields_by_name() -> None:
    """The server lease-grant frame transports DeadmanLease's fields under identical names (③)."""
    grant = set(ws.FRAME_TABLE[ws.WsFrameType.LEASE_GRANT].fields)
    canon = _canon_fields(DeadmanLease)
    # The clock-owned fields keep the canon's own names, so no reader can mistake them.
    assert {LEASE_EXPIRY_FIELD, LEASE_ISSUED_FIELD, "sequence"} <= grant
    assert {LEASE_EXPIRY_FIELD, LEASE_ISSUED_FIELD, "sequence"} <= canon
    # `lease_generation` is the transport name for the canon's `generation`.
    assert ws.LEASE_GENERATION_FIELD in grant
    assert ws.LEASE_GENERATION_CANON_FIELD in canon


def test_client_renew_frame_has_no_expiry_matching_the_canon_wire_message() -> None:
    """The client renewal transports LeaseRenewal — no expiry, so a client cannot claim life (⑤)."""
    renew = set(ws.FRAME_TABLE[ws.WsFrameType.LEASE_RENEW].fields)
    canon_renew = _canon_fields(LeaseRenewal)
    assert LEASE_EXPIRY_FIELD not in renew
    assert LEASE_EXPIRY_FIELD not in canon_renew
    assert {LEASE_ISSUED_FIELD, "sequence"} <= renew
    assert ws.client_lease_frames_omit_expiry() is True


def test_expiry_field_appears_only_on_server_authored_frames() -> None:
    """The expiry field exists only on server->client frames; no client frame carries it (⑤)."""
    for frame, spec in ws.FRAME_TABLE.items():
        if LEASE_EXPIRY_FIELD in spec.fields:
            assert spec.direction == ws.FrameDirection.SERVER_TO_CLIENT, frame


def test_reject_reasons_transport_the_canon_decisions_by_value() -> None:
    """The wire reject reasons are exactly the non-accepted RenewalDecision members (③)."""
    wire = {reason.value for reason in ws.LeaseRejectReason}
    canon_refusals = {d.value for d in RenewalDecision if d is not RenewalDecision.ACCEPTED}
    assert wire == canon_refusals


def test_replay_stale_forged_and_aged_refusals_are_all_carried() -> None:
    """Anti-replay, stale/forged generation and age-exceed each have a distinct wire reason (③)."""
    reasons = {reason.value for reason in ws.LeaseRejectReason}
    assert {
        "rejected_replay",
        "rejected_stale_generation",
        "rejected_unknown_generation",
        "discarded_aged",
        "rejected_latched",
    } <= reasons
    # The age filter's bound is named on the wire so a delayed renewal is discarded, not honoured.
    assert ws.MAX_LEASE_AGE_FIELD == "max_lease_age"


def test_rearm_handshake_is_the_three_step_canon_sequence() -> None:
    """Resume is the server-issue / operator-confirm / server-accept handshake, in order (④)."""
    assert ws.REARM_HANDSHAKE_FRAMES == (
        ws.WsFrameType.REARM_ISSUE,
        ws.WsFrameType.REARM_CONFIRM,
        ws.WsFrameType.REARM_ACCEPT,
    )
    # The canon's own machine mints a generation on issue and advances only on confirm;
    # the middle frame is the operator step, so it is the one a client authors.
    handshake = RearmHandshake(initial_generation=0)
    issued = handshake.issue()
    assert handshake.confirm() == issued
    assert (
        ws.FRAME_TABLE[ws.WsFrameType.REARM_CONFIRM].direction == ws.FrameDirection.CLIENT_TO_SERVER
    )
    assert (
        ws.FRAME_TABLE[ws.WsFrameType.REARM_ISSUE].direction == ws.FrameDirection.SERVER_TO_CLIENT
    )


def test_expiry_judge_is_pinned_to_the_server_not_the_client() -> None:
    """The WS states the server is the sole expiry judge; a client override is refused (⑤)."""
    ws.assert_expiry_owner_is_server()
    from contracts.prim import verify_expiry_owner

    with pytest.raises(PrimitiveRedefinitionError):
        verify_expiry_owner(ClockRole.CLIENT)
