"""VR UDP :5006 source binding — the minimum trust boundary (`FR-OPS-092`).

`quest_receiver`'s `:5006` datagram socket takes plaintext JSON from any host that
can reach it (`backend.teleop.vr_udp` binds `0.0.0.0` and discards the sender
address), so any host on the network can inject a pose. `FR-OPS-092` asks for HMAC or
DTLS or, at minimum, **paired source binding**: accept a datagram only from a
registered `(host, port)`.

This module is that minimum: a registry of allowed sources and a binding that refuses
a pose from anything else *before* it is parsed or used (`CG-5-08e`). It consumes the
teleoperator's own parser (`parse_datagram`) by import, so a registered source's pose
flows through the exact production parse path and nothing is re-implemented.

The fallback is explicit (`FR-OPS-092`, the `CG-5-08e` negative branch). When neither
HMAC nor DTLS is present, the VR link must be on a **dedicated isolated network**, and
that isolation must be stated as a network configuration — "it is on the LAN" is not
isolation. `NetworkIsolationFallback` refuses to certify a fallback that claims
neither a cryptographic binding nor a described isolated network.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from backend.teleop.vr_udp import FrameParseError, VrFrame, parse_datagram
from backend.teleop.vr_udp.constants import UDP_PORT_DEFAULT


@dataclass(frozen=True)
class VrSource:
    """A registered VR pose sender, identified by its network endpoint.

    Attributes:
        host: The sender's IP address (the registered/paired headset host).
        port: The sender's source port. Defaults to the `:5006` datagram port.
    """

    host: str
    port: int = UDP_PORT_DEFAULT


class VrSourceRegistry:
    """The set of `(host, port)` sources whose poses are accepted.

    Ownership: one registry per VR link. A source not registered here is refused;
    registration is the "pairing" step `FR-OPS-092` names as the minimum binding.
    """

    def __init__(self) -> None:
        """Create an empty registry — nothing is trusted until it is registered."""
        self._allowed: set[VrSource] = set()

    @property
    def allowed(self) -> frozenset[VrSource]:
        """The registered sources.

        Returns:
            (frozenset[VrSource]) The currently trusted `(host, port)` sources.
        """
        return frozenset(self._allowed)

    def register(self, host: str, port: int = UDP_PORT_DEFAULT) -> VrSource:
        """Register a source endpoint as trusted.

        Args:
            host: The sender IP to trust.
            port: The sender port to trust; defaults to `:5006`.

        Returns:
            (VrSource) The registered source.
        """
        source = VrSource(host=host, port=port)
        self._allowed.add(source)
        return source

    def is_registered(self, host: str, port: int) -> bool:
        """Whether a source endpoint is registered.

        Args:
            host: The sender IP.
            port: The sender port.

        Returns:
            (bool) True when `(host, port)` is trusted.
        """
        return VrSource(host=host, port=port) in self._allowed


class VrSourceRefusal(Enum):
    """Why a VR datagram was refused (`FR-OPS-092`)."""

    UNREGISTERED_SOURCE = "unregistered_source"
    MALFORMED_FRAME = "malformed_frame"


@dataclass(frozen=True)
class VrAcceptResult:
    """The outcome of admitting one VR datagram.

    Attributes:
        accepted: True when the source was registered and the frame parsed.
        frame: The parsed frame on acceptance, else None.
        refusal: The single reason on refusal, else None.
    """

    accepted: bool
    frame: VrFrame | None
    refusal: VrSourceRefusal | None


class VrSourceBinding:
    """Admits a VR datagram only from a registered source, then parses it.

    Ownership: holds the source registry; owns no socket. It is the source filter the
    Wave-3B `VrUdpPoseSource` lacks — the receive thread there discards the sender
    address, so this gate is where the `(host, port)` pairing is enforced. An
    unregistered source is refused before `parse_datagram` runs, so a hostile host
    cannot even reach the parser.
    """

    def __init__(self, registry: VrSourceRegistry) -> None:
        """Bind to a source registry.

        Args:
            registry: The set of trusted `(host, port)` sources.
        """
        self._registry = registry

    def accept(self, host: str, port: int, data: bytes, receive_mono_ns: int) -> VrAcceptResult:
        """Admit and parse one datagram, or refuse it by source or malformation.

        Args:
            host: The datagram's source IP.
            port: The datagram's source port.
            data: One newline-terminated JSON frame's bytes.
            receive_mono_ns: The PC receive instant to stamp on the parsed frame.

        Returns:
            (VrAcceptResult) Accepted with the parsed frame, or refused with a reason.
            An unregistered source is refused before the frame is parsed.
        """
        if not self._registry.is_registered(host, port):
            return VrAcceptResult(
                accepted=False, frame=None, refusal=VrSourceRefusal.UNREGISTERED_SOURCE
            )
        try:
            frame = parse_datagram(data, receive_mono_ns)
        except FrameParseError:
            return VrAcceptResult(
                accepted=False, frame=None, refusal=VrSourceRefusal.MALFORMED_FRAME
            )
        return VrAcceptResult(accepted=True, frame=frame, refusal=None)


class NetworkIsolationError(ValueError):
    """Raised when a fallback claims neither a crypto binding nor an isolated network."""


@dataclass(frozen=True)
class NetworkIsolationFallback:
    """The `FR-OPS-092` fallback when HMAC/DTLS is absent: a dedicated isolated network.

    The fallback is only valid if it either carries a cryptographic binding, or states
    a described isolated network. A claim of neither — implicitly trusting the LAN — is
    refused, because "it is on the LAN" is not isolation (`CG-5-08e` negative branch).

    Attributes:
        hmac_present: Whether HMAC authentication is applied to the VR link.
        dtls_present: Whether DTLS is applied to the VR link.
        isolated_network: Whether the VR link is on a dedicated isolated network.
        network_description: The network configuration that realises the isolation —
            required when relying on isolation, and must not be an empty claim.
    """

    hmac_present: bool
    dtls_present: bool
    isolated_network: bool
    network_description: str

    def __post_init__(self) -> None:
        """Reject a fallback that relies on neither crypto nor a described isolated net."""
        if self.hmac_present or self.dtls_present:
            return
        if not self.isolated_network or not self.network_description.strip():
            raise NetworkIsolationError(
                "VR link has no HMAC/DTLS and no described isolated network; a plaintext UDP "
                "link on the shared LAN is not a trust boundary (FR-OPS-092)"
            )

    @property
    def cryptographically_bound(self) -> bool:
        """Whether the link has a cryptographic binding (HMAC or DTLS).

        Returns:
            (bool) True when HMAC or DTLS is present.
        """
        return self.hmac_present or self.dtls_present

    def describe(self) -> str:
        """Return the network-configuration statement of how the link is protected.

        Returns:
            (str) A one-line description of the applied protection.
        """
        if self.cryptographically_bound:
            bindings = [
                name
                for name, present in (("HMAC", self.hmac_present), ("DTLS", self.dtls_present))
                if present
            ]
            return f"VR link cryptographically bound via {', '.join(bindings)}"
        return f"VR link on dedicated isolated network: {self.network_description}"
