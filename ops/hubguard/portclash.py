"""Startup port-clash detection — refuse to start on a duplicate or taken port.

FR-SYS-026 and spec 01 §2.17: the web backend and openpi both default to port
8000, so a deployment that enables both must reconfigure one. Detection has two
independent sources — a manifest duplicate (two enabled services declaring one
port) and a live bind failure (the port is already held by another process) — and
either one refuses startup, naming the port and the contending services rather
than letting a second binder fail obscurely later.
"""

from __future__ import annotations

import socket
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from operator import attrgetter
from typing import Protocol

# Canonical default port map (FR-SYS-026 / §2.17). The web backend and openpi share
# 8000, which is the clash this detector exists to catch; openpi ships disabled so
# the default map starts cleanly and enabling openpi is what surfaces the conflict.
WEB_BACKEND_PORT = 8000
OPENPI_WS_PORT = 8000
POLICY_SERVER_GRPC_PORT = 8080
GROOT_ZMQ_PORT = 5555
VR_UDP_PORT = 5006
WEBXR_HTTPS_PORT = 8443

DEFAULT_PROBE_HOST = "127.0.0.1"


@dataclass(frozen=True)
class ServiceEndpoint:
    """One configurable service port in the startup map.

    Attributes:
        name: Human-facing service name, shown in a clash report.
        port: TCP/UDP port the service binds.
        enabled: Whether this deployment starts the service. A disabled service
            reserves no port and cannot clash.
    """

    name: str
    port: int
    enabled: bool


DEFAULT_PORT_MAP: tuple[ServiceEndpoint, ...] = (
    ServiceEndpoint(name="web-backend", port=WEB_BACKEND_PORT, enabled=True),
    ServiceEndpoint(name="policy-server-grpc", port=POLICY_SERVER_GRPC_PORT, enabled=True),
    ServiceEndpoint(name="groot-zmq", port=GROOT_ZMQ_PORT, enabled=True),
    ServiceEndpoint(name="vr-udp", port=VR_UDP_PORT, enabled=True),
    ServiceEndpoint(name="webxr-https", port=WEBXR_HTTPS_PORT, enabled=True),
    ServiceEndpoint(name="openpi-ws", port=OPENPI_WS_PORT, enabled=False),
)


class ClashSource(StrEnum):
    """Which of the two detectors reported a clash."""

    MANIFEST = "manifest"
    BIND = "bind"


@dataclass(frozen=True)
class PortClash:
    """A single detected port conflict.

    Attributes:
        port: The conflicting port.
        source: Whether the conflict is a manifest duplicate or a live bind.
        services: Names of the enabled services contending for the port.
    """

    port: int
    source: ClashSource
    services: tuple[str, ...]

    def __str__(self) -> str:
        contenders = ", ".join(self.services)
        return f"port {self.port} [{self.source.value}]: {contenders}"


class PortClashError(Exception):
    """Startup is refused because one or more ports conflict (OA-SYS-014)."""

    def __init__(self, clashes: Sequence[PortClash]) -> None:
        detail = "; ".join(str(clash) for clash in clashes)
        super().__init__(f"port clash detected, refusing to start: {detail}")
        self.clashes = tuple(clashes)


class PortProbe(Protocol):
    """Reports whether a port is already held on a host.

    Injected so the manifest and bind detectors can be tested without opening real
    sockets, and so a live probe can be swapped for one host-family or another.
    """

    def __call__(self, host: str, port: int) -> bool: ...


def _port_in_use(host: str, port: int) -> bool:
    """Report whether a TCP port is already bound on the host.

    Binds a throwaway socket without address reuse: a bind that raises `OSError`
    means another socket already holds the port. This is a best-effort pre-flight
    with an inherent time-of-check/time-of-use gap — a port free now can be taken
    before the real service binds — which is why manifest detection runs alongside
    it rather than trusting the probe alone.

    Args:
        host: Host to probe.
        port: TCP port to test.

    Returns:
        (bool) True when the port is already held.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((host, port))
        except OSError:
            return True
    return False


def manifest_clashes(endpoints: Sequence[ServiceEndpoint]) -> list[PortClash]:
    """Find ports claimed by more than one enabled service.

    Args:
        endpoints: The configured service map.

    Returns:
        (list[PortClash]) One clash per over-subscribed port, ascending by port.
    """
    by_port: dict[int, list[str]] = {}
    for endpoint in endpoints:
        if endpoint.enabled:
            by_port.setdefault(endpoint.port, []).append(endpoint.name)
    return [
        PortClash(port=port, source=ClashSource.MANIFEST, services=tuple(names))
        for port, names in sorted(by_port.items())
        if len(names) > 1
    ]


def bind_clashes(
    endpoints: Sequence[ServiceEndpoint],
    host: str = DEFAULT_PROBE_HOST,
    probe: PortProbe = _port_in_use,
) -> list[PortClash]:
    """Find enabled ports already held by another process on the host.

    Args:
        endpoints: The configured service map.
        host: Host to probe the ports on.
        probe: The port-liveness probe.

    Returns:
        (list[PortClash]) One clash per taken port, ascending by port.
    """
    return [
        PortClash(port=endpoint.port, source=ClashSource.BIND, services=(endpoint.name,))
        for endpoint in sorted(endpoints, key=attrgetter("port"))
        if endpoint.enabled and probe(host, endpoint.port)
    ]


def verify_startup(
    endpoints: Sequence[ServiceEndpoint] = DEFAULT_PORT_MAP,
    host: str = DEFAULT_PROBE_HOST,
    probe: PortProbe = _port_in_use,
) -> None:
    """Refuse startup when any port conflicts, from either detector.

    Args:
        endpoints: The configured service map.
        host: Host to probe live binds on.
        probe: The port-liveness probe.

    Raises:
        PortClashError: One or more ports conflict; the arm-side services must not
            start until the operator reconfigures a port.
    """
    clashes = manifest_clashes(endpoints) + bind_clashes(endpoints, host, probe)
    if clashes:
        raise PortClashError(clashes)
