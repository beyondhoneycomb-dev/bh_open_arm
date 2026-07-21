"""Emission acceptance: the runtime path rejects unregistered codes.

Acceptance ⑦ (runtime half). A registered code resolves to its row and English
message; an unregistered string is rejected rather than emitted, which is the
runtime twin of the static inline-literal ban.
"""

from __future__ import annotations

import pytest

from contracts.errors import codes, make_error
from contracts.errors.emission import OaError, emit
from contracts.errors.registry import REGISTRY, UnregisteredCodeError


def test_registered_code_resolves() -> None:
    """A registered code carries its row's English message."""
    error = make_error(codes.OA_CAN_004)
    assert error.code == "OA-CAN-004"
    assert error.entry.message_en in str(error)


def test_unregistered_code_is_rejected() -> None:
    """Emitting a code no row backs raises rather than fabricating one."""
    with pytest.raises(UnregisteredCodeError):
        make_error("OA-CAN-999")


def test_unregistered_code_in_raise_is_rejected() -> None:
    """Constructing the exception directly is guarded the same way."""
    with pytest.raises(UnregisteredCodeError):
        raise OaError("OA-ZZZ-001")


def test_emit_hands_structured_event_to_sink() -> None:
    """A registered emission produces a structured event for the logger sink."""
    captured: list[dict[str, object]] = []
    event = emit(captured.append, codes.OA_MOT_00B, joint="left_4")
    assert captured == [event]
    assert event["code"] == "OA-MOT-00B"
    assert event["severity"] == REGISTRY.get(codes.OA_MOT_00B).severity
    assert event["joint"] == "left_4"


def test_emit_rejects_unregistered() -> None:
    """The sink is never called for an unregistered code."""
    captured: list[dict[str, object]] = []
    with pytest.raises(UnregisteredCodeError):
        emit(captured.append, "OA-CAN-999")
    assert captured == []
