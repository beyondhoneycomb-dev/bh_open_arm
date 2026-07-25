"""CG-5-08e — a VR pose from an unregistered source is refused (FR-OPS-092).

The `:5006` datagram path trusts nobody until paired: a pose is admitted only from a
registered `(host, port)`, and an unregistered source is refused before the frame is
even parsed. The fallback when neither HMAC nor DTLS is present must be a described
isolated network, not an implicit trust of the LAN.
"""

from __future__ import annotations

import json

import pytest

from backend.security.vr_source_binding import (
    NetworkIsolationError,
    NetworkIsolationFallback,
    VrSourceBinding,
    VrSourceRefusal,
    VrSourceRegistry,
)
from backend.teleop.vr_udp.constants import UDP_PORT_DEFAULT

_REGISTERED_HOST = "10.0.0.42"
_UNREGISTERED_HOST = "10.0.0.99"
_RECEIVE_MONO_NS = 1_000_000

_VALID_FRAME = json.dumps(
    {
        "t": 1.0,
        "v": 0,
        "vl": 0,
        "vr": 0,
        "lc": [0.0, 0.0, 0.0],
        "rc": [0.0, 0.0, 0.0],
        "lt": [0.0, 0.0, 0.0, 1.0],
        "rt": [0.0, 0.0, 0.0, 1.0],
    }
).encode("utf-8")


def _binding() -> VrSourceBinding:
    registry = VrSourceRegistry()
    registry.register(_REGISTERED_HOST, UDP_PORT_DEFAULT)
    return VrSourceBinding(registry)


def test_registered_source_pose_is_accepted_and_parsed() -> None:
    binding = _binding()
    result = binding.accept(_REGISTERED_HOST, UDP_PORT_DEFAULT, _VALID_FRAME, _RECEIVE_MONO_NS)
    assert result.accepted is True
    assert result.frame is not None
    assert result.refusal is None


def test_unregistered_host_is_refused_before_parse() -> None:
    binding = _binding()
    result = binding.accept(_UNREGISTERED_HOST, UDP_PORT_DEFAULT, _VALID_FRAME, _RECEIVE_MONO_NS)
    assert result.accepted is False
    assert result.frame is None
    assert result.refusal is VrSourceRefusal.UNREGISTERED_SOURCE


def test_registered_host_wrong_port_is_refused() -> None:
    binding = _binding()
    result = binding.accept(_REGISTERED_HOST, UDP_PORT_DEFAULT + 1, _VALID_FRAME, _RECEIVE_MONO_NS)
    assert result.refusal is VrSourceRefusal.UNREGISTERED_SOURCE


def test_registered_source_malformed_frame_is_reported() -> None:
    binding = _binding()
    result = binding.accept(_REGISTERED_HOST, UDP_PORT_DEFAULT, b"{not json", _RECEIVE_MONO_NS)
    assert result.accepted is False
    assert result.refusal is VrSourceRefusal.MALFORMED_FRAME


def test_registry_membership() -> None:
    registry = VrSourceRegistry()
    registry.register(_REGISTERED_HOST)
    assert registry.is_registered(_REGISTERED_HOST, UDP_PORT_DEFAULT)
    assert not registry.is_registered(_UNREGISTERED_HOST, UDP_PORT_DEFAULT)


def test_isolated_network_fallback_is_valid_when_described() -> None:
    fallback = NetworkIsolationFallback(
        hmac_present=False,
        dtls_present=False,
        isolated_network=True,
        network_description="dedicated VLAN 90, no gateway route to the office LAN",
    )
    assert not fallback.cryptographically_bound
    assert "dedicated VLAN 90" in fallback.describe()


def test_crypto_binding_fallback_is_valid() -> None:
    fallback = NetworkIsolationFallback(
        hmac_present=True,
        dtls_present=False,
        isolated_network=False,
        network_description="",
    )
    assert fallback.cryptographically_bound
    assert "HMAC" in fallback.describe()


def test_lan_is_not_isolation() -> None:
    with pytest.raises(NetworkIsolationError):
        NetworkIsolationFallback(
            hmac_present=False,
            dtls_present=False,
            isolated_network=False,
            network_description="",
        )


def test_isolation_claim_needs_a_description() -> None:
    with pytest.raises(NetworkIsolationError):
        NetworkIsolationFallback(
            hmac_present=False,
            dtls_present=False,
            isolated_network=True,
            network_description="   ",
        )
