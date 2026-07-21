"""WP-OPS-04 acceptance ⑤ — startup detects a port clash and refuses to start,
from both a manifest duplicate and a live already-held port.

The named clash is the web-backend/openpi 8000 collision of §2.17; the live-bind
path is exercised against a real socket so the detector is proven to catch an
occupied port, not merely compare a dict.
"""

from __future__ import annotations

import socket
from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from ops.hubguard.portclash import (
    DEFAULT_PORT_MAP,
    WEB_BACKEND_PORT,
    ClashSource,
    PortClashError,
    ServiceEndpoint,
    _port_in_use,
    bind_clashes,
    manifest_clashes,
    verify_startup,
)
from tests.wpops04.doubles import MapProbe

_ALL_FREE = MapProbe(busy_ports=())
_LOCALHOST = "127.0.0.1"


def _map_with_openpi_enabled() -> tuple[ServiceEndpoint, ...]:
    """The default map with openpi turned on — the 8000 collision fixture."""
    return tuple(
        endpoint
        if endpoint.name != "openpi-ws"
        else ServiceEndpoint(name=endpoint.name, port=endpoint.port, enabled=True)
        for endpoint in DEFAULT_PORT_MAP
    )


@contextmanager
def _held_port() -> Iterator[int]:
    """Bind an ephemeral localhost port for the duration of the block."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as holder:
        holder.bind((_LOCALHOST, 0))
        holder.listen()
        yield holder.getsockname()[1]


# --- Acceptance ⑤ : the 8000 manifest collision is detected and refuses startup.


def test_openpi_and_web_backend_both_on_8000_is_a_manifest_clash() -> None:
    clashes = manifest_clashes(_map_with_openpi_enabled())
    assert len(clashes) == 1
    clash = clashes[0]
    assert clash.port == WEB_BACKEND_PORT == 8000
    assert clash.source is ClashSource.MANIFEST
    assert set(clash.services) == {"web-backend", "openpi-ws"}


def test_startup_refuses_on_the_8000_collision() -> None:
    with pytest.raises(PortClashError) as excinfo:
        verify_startup(_map_with_openpi_enabled(), host=_LOCALHOST, probe=_ALL_FREE)
    assert any(clash.port == 8000 for clash in excinfo.value.clashes)


# --- The default map is clean, so the detector is not a false-positive machine.


def test_default_map_starts_cleanly_when_all_ports_free() -> None:
    verify_startup(DEFAULT_PORT_MAP, host=_LOCALHOST, probe=_ALL_FREE)


def test_default_map_has_no_manifest_clash() -> None:
    assert manifest_clashes(DEFAULT_PORT_MAP) == []


# --- Live-bind detection against a real occupied socket.


def test_live_probe_reports_held_and_free_ports() -> None:
    with _held_port() as held:
        assert _port_in_use(_LOCALHOST, held) is True
    # Once the holder is closed the port is free again.
    with _held_port() as previously_held:
        pass
    assert _port_in_use(_LOCALHOST, previously_held) is False


def test_startup_refuses_when_a_configured_port_is_already_held() -> None:
    with _held_port() as held:
        endpoints = (ServiceEndpoint(name="web-backend", port=held, enabled=True),)
        clashes = bind_clashes(endpoints, host=_LOCALHOST)
        assert len(clashes) == 1
        assert clashes[0].source is ClashSource.BIND
        with pytest.raises(PortClashError):
            verify_startup(endpoints, host=_LOCALHOST)


def test_disabled_service_on_a_held_port_does_not_clash() -> None:
    with _held_port() as held:
        endpoints = (ServiceEndpoint(name="openpi-ws", port=held, enabled=False),)
        assert bind_clashes(endpoints, host=_LOCALHOST) == []


def test_injected_busy_probe_triggers_refusal() -> None:
    endpoints = (ServiceEndpoint(name="web-backend", port=WEB_BACKEND_PORT, enabled=True),)
    with pytest.raises(PortClashError):
        verify_startup(endpoints, host=_LOCALHOST, probe=MapProbe(busy_ports=(WEB_BACKEND_PORT,)))
