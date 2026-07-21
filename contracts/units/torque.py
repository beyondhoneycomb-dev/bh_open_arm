"""Torque in physical units, and the one crossing to raw packet scale.

`03` FR-MOT-037 clamps torque in newton-metres, a different axis from the DM
`T_MAX` packet scale: the same packet number is a different torque on a DM8009
(J1/J2) than on a DM4310 (J5-J7), so a clamp expressed in `Nm` must never receive
a packet value. `clamp_torque` therefore takes `Nm` on every parameter; the type
rejects a packet-scale value before any arithmetic runs.

The clamp holds no threshold of its own. The per-motor limits (`10` §2.3:
DM8009 +/-54, DM4340 +/-28, DM4310 +/-10 Nm) and the more conservative dry-run
safety limits live with their owners; this contract freezes the *unit*, not the
value, so a caller supplies the limit as an `Nm` and the boundary between packet
and physical scale is crossed only through `packet_to_nm` / `nm_to_packet`.
"""

from __future__ import annotations

from contracts.units.tags import Nm, PacketTorque


def clamp_torque(torque: Nm, limit: Nm) -> Nm:
    """Clamp a torque to a symmetric physical limit.

    Args:
        torque: The torque to clamp, in newton-metres.
        limit: The symmetric bound, in newton-metres; its magnitude is used.

    Returns:
        (Nm) The torque bounded to the closed interval [-|limit|, +|limit|].
    """
    bound = abs(limit.value)
    return Nm(max(-bound, min(bound, torque.value)))


def packet_to_nm(packet: PacketTorque, nm_per_count: float) -> Nm:
    """Convert a raw packet-scale torque to newton-metres.

    Args:
        packet: A torque in raw motor-packet counts.
        nm_per_count: The per-motor scale, newton-metres per packet count. It is
            supplied by the caller because it is motor-specific and not owned by
            this contract.

    Returns:
        (Nm) The torque in newton-metres.
    """
    return Nm(packet.value * nm_per_count)


def nm_to_packet(torque: Nm, nm_per_count: float) -> PacketTorque:
    """Convert a physical torque to raw packet-scale counts.

    Args:
        torque: A torque in newton-metres.
        nm_per_count: The per-motor scale, newton-metres per packet count.

    Returns:
        (PacketTorque) The torque in raw motor-packet counts, rounded to integer.

    Raises:
        ValueError: If `nm_per_count` is zero, which has no inverse.
    """
    if nm_per_count == 0.0:
        raise ValueError("nm_per_count must be non-zero to invert the packet scale")
    return PacketTorque(round(torque.value / nm_per_count))
