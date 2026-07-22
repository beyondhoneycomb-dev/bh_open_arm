"""Pattern B — the read-only RX tap: decode runs here, the live open and the OS block.

The frame decode is pure and runs on synthetic bytes. Opening a real CAN socket needs an
interface, so that is the deferred boundary. The read-only guarantee — that shutting the
write half makes a transmit fail — is proven here on a socket pair, so the mechanism is
shown to bite even though the CAN interface is deferred.
"""

from __future__ import annotations

import socket

import pytest

from backend.friction_log.rx_tap import (
    CAN_FRAME_SIZE,
    _shut_write_half,
    decode_can_frame,
    encode_can_frame,
    open_rx_only_socket,
)

_ABSENT_INTERFACE = "wp2b05nope0"


def test_decode_round_trips_an_encoded_frame() -> None:
    """A frame encoded then decoded returns the original id and payload."""
    frame = encode_can_frame(0x123, b"\x01\x02\x03")
    assert len(frame) == CAN_FRAME_SIZE
    assert decode_can_frame(frame) == (0x123, b"\x01\x02\x03")


def test_decode_rejects_a_wrong_width_frame() -> None:
    """A buffer that is not a full can_frame is rejected, not silently misread."""
    with pytest.raises(ValueError, match="can_frame"):
        decode_can_frame(b"\x00" * (CAN_FRAME_SIZE - 1))


def test_encode_rejects_an_oversized_payload() -> None:
    """A CAN frame carries at most 8 data bytes."""
    with pytest.raises(ValueError, match="8 data bytes"):
        encode_can_frame(0x1, b"\x00" * 9)


def test_open_rx_only_socket_defers_without_a_can_interface() -> None:
    """Opening a real CAN interface is the deferred boundary: it raises without one."""
    with pytest.raises(OSError):
        open_rx_only_socket(_ABSENT_INTERFACE)


def test_shutting_the_write_half_makes_a_transmit_fail() -> None:
    """The read-only mechanism bites: after the write half is shut, a send raises."""
    left, right = socket.socketpair()
    try:
        _shut_write_half(left)
        with pytest.raises(OSError):
            left.sendall(b"\x01")
    finally:
        left.close()
        right.close()
