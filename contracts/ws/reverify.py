"""The reverify hook for CTR-WS@v1: the body agrees with CTR-PRIM, the frozen file with the source.

The frozen body `contracts/ws/envelope.schema.json` (`CONTRACT_FROZEN`, frozen by
`WP-3A-06`) is a projection of `schema.py` via `canonical_envelope()`. Two things can
still go wrong and neither the freeze hash alone would catch until 3B amplified it:

- the typed surface drifts from `CTR-PRIM@v1` — a priority that is no longer the
  primitive's, an expiry field that is no longer the pinned one, a camera tag that no
  longer round-trips the primitive's join, an expiry judge that is no longer the
  server. These are checked against the primitive, the external truth, every run.
- the frozen file on disk drifts from the generator — a hand edit to the frozen JSON
  that no longer equals `envelope_json()`. This is checked only once the file exists
  (after `WP-3A-06` freezes it); until then the contract is DRAFT and the frozen path
  is deliberately absent, so its own check is vacuous rather than failing.

This is a real predicate, proven against the generated body, not a re-hash of it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from contracts.prim import (
    EXPIRY_JUDGE_ROLE,
    LEASE_EXPIRY_FIELD,
    LEASE_ISSUED_FIELD,
    WS_TAG_SEPARATOR,
    CameraSlotKey,
    FrameType,
    PriorityClass,
    arm_slot,
)
from contracts.ws.schema import (
    CONTRACT_ID,
    FRAME_TABLE,
    LeaseRejectReason,
    WsFrameType,
    assert_expiry_owner_is_server,
    camera_frame_tag,
    canonical_envelope,
    client_lease_frames_omit_expiry,
    envelope_json,
    slot_from_camera_frame_tag,
)

# The frozen body's path, alongside this module. Absent while CTR-WS@v1 is DRAFT
# (WP-3A-06 writes it here from `envelope_json()` and freezes it); the on-disk drift
# check activates once the file exists.
ENVELOPE_PATH = Path(__file__).parent / "envelope.schema.json"


@dataclass(frozen=True)
class ReverifyReport:
    """The verdict of re-verifying the generated body against CTR-PRIM and the frozen file.

    Attributes:
        confirmed: True only when every consistency check passed.
        checks: The names of the checks that were evaluated.
        mismatches: One message per failed check; empty when confirmed.
    """

    confirmed: bool
    checks: tuple[str, ...]
    mismatches: tuple[str, ...]


_CHECK_CONTRACT_ID = "contract_id_matches"
_CHECK_SINGLE_CHANNEL = "single_realtime_channel"
_CHECK_PRIORITIES = "priorities_are_ctr_prim"
_CHECK_LEASE_FIELDS = "lease_fields_are_ctr_prim_pins"
_CHECK_EXPIRY_OWNER = "expiry_judge_is_server"
_CHECK_CLIENT_NO_EXPIRY = "client_frames_omit_expiry"
_CHECK_CAMERA_JOIN = "camera_tag_round_trips"
_CHECK_REJECT_REASONS = "reject_reasons_present"
_CHECK_SECURITY = "security_floor_present"
_CHECK_HEALTH = "health_redaction_present"
_CHECK_FROZEN_FILE = "frozen_file_matches_generator"

_CHECKS = (
    _CHECK_CONTRACT_ID,
    _CHECK_SINGLE_CHANNEL,
    _CHECK_PRIORITIES,
    _CHECK_LEASE_FIELDS,
    _CHECK_EXPIRY_OWNER,
    _CHECK_CLIENT_NO_EXPIRY,
    _CHECK_CAMERA_JOIN,
    _CHECK_REJECT_REASONS,
    _CHECK_SECURITY,
    _CHECK_HEALTH,
    _CHECK_FROZEN_FILE,
)


def _camera_tag_round_trips() -> bool:
    """Whether a camera slot survives the WS tag join and its inverse for both channels."""
    slot: CameraSlotKey = arm_slot("left", "wrist")
    return all(
        slot_from_camera_frame_tag(camera_frame_tag(slot, channel)) == slot for channel in FrameType
    )


def reverify_body(document: dict[str, Any]) -> ReverifyReport:
    """Confirm the generated envelope body agrees with `CTR-PRIM@v1` and the mirror.

    Args:
        document: The body produced by `canonical_envelope()`.

    Returns:
        (ReverifyReport) The verdict; `confirmed` only when every check passes.
    """
    mismatches: list[str] = []

    if document["contract"] != CONTRACT_ID:
        mismatches.append(f"body contract {document['contract']!r} is not {CONTRACT_ID}")

    transport = document["transport"]
    if transport["realtime_channel"] != "websocket" or not transport["single_realtime_channel"]:
        mismatches.append("the body does not assert a single WebSocket realtime channel")

    for name, spec in document["frame_types"].items():
        frame = WsFrameType(name)
        if spec["priority"] != int(FRAME_TABLE[frame].priority):
            mismatches.append(f"frame {name!r} priority is not its CTR-PRIM@v1 queue priority")
    priority_classes = document["queues"]["priority_classes"]
    for member in PriorityClass:
        if priority_classes.get(member.name.lower()) != int(member):
            mismatches.append(f"priority class {member.name} is not CTR-PRIM@v1's value")
    if not document["queues"]["lease_is_highest_priority"]:
        mismatches.append("the body does not pin the lease class as highest priority")

    lease = document["lease"]
    if lease["expiry_field"] != LEASE_EXPIRY_FIELD or lease["issued_field"] != LEASE_ISSUED_FIELD:
        mismatches.append("a lease field is not the CTR-PRIM@v1 pin")

    try:
        assert_expiry_owner_is_server()
        if lease["expiry_judge_role"] != EXPIRY_JUDGE_ROLE.value:
            mismatches.append("the body expiry judge role is not the pinned server role")
    except Exception as error:  # noqa: BLE001 — a pin failure is a check failure, reported not raised
        mismatches.append(f"expiry-owner pin rejected the server role: {error}")

    if not lease["client_frame_carries_no_expiry"] or not client_lease_frames_omit_expiry():
        mismatches.append("a client-authored lease frame carries the expiry field")

    if not _camera_tag_round_trips():
        mismatches.append("the camera frame tag does not round-trip through the CTR-PRIM@v1 join")
    if document["frame_types"]["camera"]["tag_separator"] != WS_TAG_SEPARATOR:
        mismatches.append("the camera tag separator is not the CTR-PRIM@v1 separator")

    if set(lease["reject_reasons"]) != {reason.value for reason in LeaseRejectReason}:
        mismatches.append("the lease reject reasons differ from the mirror")

    security = document["security"]
    if security["scheme"] != "wss" or not security["wildcard_origin_forbidden"]:
        mismatches.append("the body security floor is not WSS with a wildcard-Origin ban")

    if tuple(document["health"]["forbidden_fields"]) != ("control_holder", "active_profile"):
        mismatches.append("the health forbidden-field set differs from the mirror")

    if ENVELOPE_PATH.is_file() and ENVELOPE_PATH.read_text(encoding="utf-8") != envelope_json():
        mismatches.append("the frozen envelope file on disk differs from the generator")

    return ReverifyReport(confirmed=not mismatches, checks=_CHECKS, mismatches=tuple(mismatches))


def reverify() -> ReverifyReport:
    """Run the reverify hook against the freshly generated envelope body.

    Returns:
        (ReverifyReport) The verdict for the current typed surface.
    """
    return reverify_body(canonical_envelope())


__all__ = [
    "ENVELOPE_PATH",
    "ReverifyReport",
    "reverify",
    "reverify_body",
]
