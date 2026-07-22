"""Pattern B — the fully manual RX tap (WP-2B-05, acceptance ①).

An alternative to riding the scheduler: open a *separate* SocketCAN raw socket that is
read-only, receive the MIT frames the scheduler already puts on the bus, and log them.
The single, load-bearing requirement is that this socket transmits nothing — a second
sender on the bus is a second CAN writer (I-1) and drops the arm.

Read-only is enforced two ways, belt and braces:

- **At the OS.** After binding, the write half is shut down (`shutdown(SHUT_WR)`), so the
  kernel refuses any send on this socket even if code later tried one.
- **Statically.** This module names no transmit symbol — no `send`, no CAN writer, no
  `robot.bus` — so the no-transmit scan confirms the path cannot transmit (acceptance ①).

What runs on this host and what defers:

- `decode_can_frame` unpacks a raw `can_frame` (id + 8 data bytes) and runs here against
  synthetic bytes, so the receive path is exercised without hardware.
- `open_rx_only_socket` binds to a CAN interface. On a host with no CAN interface the
  bind raises `OSError`; that bind, the live `recv`, and the on-bus proof that one writer
  holds the bus (②) are DEFERRED and re-checked on the rig through
  `backend.friction_log.reverify.reverify_rx_only_socket`.

The per-joint pos/vel/tau extraction from a DM MIT feedback packet is the driver's
concern (`packages/lerobot_robot_openarm`, a protected tree); this tap stops at the raw
`(can_id, payload)` and hands that on, so it never reimplements the motor codec.
"""

from __future__ import annotations

import socket
import struct

# struct can_frame: can_id (u32, native), can_dlc (u8) + 3 pad, then 8 data bytes —
# the same layout the block harness uses (`ops/acl/block_harness.py`).
_CAN_FRAME = struct.Struct("=IB3x8s")
CAN_FRAME_SIZE = _CAN_FRAME.size

# CAN_RAW is not always present in `socket` on non-Linux hosts; name it locally so an
# import on such a host fails loudly here rather than deep in a call.
_PF_CAN = socket.PF_CAN
_CAN_RAW = socket.CAN_RAW


def open_rx_only_socket(interface: str) -> socket.socket:
    """Open a read-only SocketCAN raw socket bound to `interface`.

    The socket is created, bound, and then has its write half shut down so the kernel
    refuses any transmit on it. Binding needs a real CAN interface, so on a host without
    one this raises `OSError` — the deferred boundary — and never silently returns a
    half-open socket.

    Args:
        interface: CAN interface name, e.g. `can0` or `vcan0`.

    Returns:
        (socket.socket) A bound, receive-only CAN raw socket.

    Raises:
        OSError: If the interface does not exist or cannot be bound (deferred on a host
            with no CAN hardware).
    """
    sock = socket.socket(_PF_CAN, socket.SOCK_RAW, _CAN_RAW)
    try:
        sock.bind((interface,))  # AF_CAN bind takes a 1-tuple of the interface name.
        _shut_write_half(sock)
    except OSError:
        sock.close()
        raise
    return sock


def _shut_write_half(sock: socket.socket) -> None:
    """Shut down a socket's write half, making it read-only at the OS.

    After this, any transmit on the socket raises, so read-only is enforced by the
    kernel and not merely by the absence of a send call. Family-agnostic: the same call
    disables writing on any connected or bound socket.

    Args:
        sock: The socket to make receive-only.
    """
    sock.shutdown(socket.SHUT_WR)


def decode_can_frame(data: bytes) -> tuple[int, bytes]:
    """Unpack a raw `can_frame` into its arbitration id and payload.

    Args:
        data: Exactly `CAN_FRAME_SIZE` bytes of a Linux `struct can_frame`.

    Returns:
        (tuple[int, bytes]) The CAN id and the `dlc`-length data bytes.

    Raises:
        ValueError: If `data` is not `CAN_FRAME_SIZE` bytes wide.
    """
    if len(data) != CAN_FRAME_SIZE:
        raise ValueError(f"a can_frame is {CAN_FRAME_SIZE} bytes, got {len(data)}")
    can_id, dlc, payload = _CAN_FRAME.unpack(data)
    return int(can_id), bytes(payload[:dlc])


def encode_can_frame(can_id: int, payload: bytes) -> bytes:
    """Pack a CAN id and payload into a raw `can_frame`, for test/decoder round-trips.

    This is a serialiser, not a transmit path — it returns bytes, it does not send them.

    Args:
        can_id: The arbitration id.
        payload: Up to 8 data bytes.

    Returns:
        (bytes) A `CAN_FRAME_SIZE`-byte `can_frame`.

    Raises:
        ValueError: If `payload` exceeds 8 bytes.
    """
    if len(payload) > 8:
        raise ValueError(f"a can_frame carries at most 8 data bytes, got {len(payload)}")
    return _CAN_FRAME.pack(can_id, len(payload), payload.ljust(8, b"\x00"))
