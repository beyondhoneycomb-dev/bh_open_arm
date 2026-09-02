"""Read the declared port map.

The numbers live in `01` §2.17 and `14` §2.1 as markdown tables, which is where they were
decided and where they stay. This module reads the machine-readable copy beside it; a mirror
test compares the two, so the copy cannot quietly drift from the tables that own it.

Nothing here judges. A port conflict is `FR-OPS-066`'s business and it is decided against what
is actually listening, not against this list — a declaration cannot conflict with itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

CANON_PATH = Path(__file__).resolve().parent / "port_map.yaml"

COMPONENTS_KEY = "components"
COMPONENT_FIELD = "component"
PROTOCOL_FIELD = "protocol"
PORT_FIELD = "port"
SERVED_HERE_FIELD = "served_by_this_process"


class PortCanonError(RuntimeError):
    """Raised when the declaration cannot be read as a port map."""


@dataclass(frozen=True)
class CanonPort:
    """One declared component and the port it is expected on.

    Attributes:
        component: The component's name, as the spec tables write it.
        protocol: What speaks on that port.
        port: The expected port, or None for a component with no network boundary. None is
            a declaration, not a gap: it is what lets a compare view say "no port expected"
            rather than reporting a missing binding.
        served_by_this_process: Whether this row is the one `oa-serve` fills. The compare view
            lines bindings up against the canon by component name, so the server has to know
            which name is its own; matching on a port instead would break the moment `--port`
            moves, which is exactly the case that view exists to show.
    """

    component: str
    protocol: str
    port: int | None
    served_by_this_process: bool


def _row(entry: Any) -> CanonPort:
    """Read one declared row, refusing anything that is not one."""
    if not isinstance(entry, dict):
        raise PortCanonError(f"port map entry is not a mapping: {entry!r}")
    component = entry.get(COMPONENT_FIELD)
    protocol = entry.get(PROTOCOL_FIELD)
    port = entry.get(PORT_FIELD)
    if not isinstance(component, str) or not isinstance(protocol, str):
        raise PortCanonError(f"port map entry is missing a name or a protocol: {entry!r}")
    # A bool is checked before int because `bool` is an `int` in Python, and `True` would
    # otherwise declare a component on port 1.
    if port is not None and (isinstance(port, bool) or not isinstance(port, int)):
        raise PortCanonError(f"{component}: port {port!r} is not a port number or null")
    return CanonPort(
        component=component,
        protocol=protocol,
        port=port,
        served_by_this_process=entry.get(SERVED_HERE_FIELD, False) is True,
    )


def load_port_canon() -> tuple[CanonPort, ...]:
    """Load the declared port map in declaration order.

    Returns:
        (tuple[CanonPort, ...]) Every declared component.

    Raises:
        PortCanonError: If the file is unreadable or is not a list of port rows.
    """
    try:
        document = yaml.safe_load(CANON_PATH.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as unreadable:
        raise PortCanonError(f"{CANON_PATH} could not be read: {unreadable}") from unreadable
    if not isinstance(document, dict) or not isinstance(document.get(COMPONENTS_KEY), list):
        raise PortCanonError(f"{CANON_PATH} has no {COMPONENTS_KEY!r} list")
    return tuple(_row(entry) for entry in document[COMPONENTS_KEY])


def served_component() -> str:
    """The canon component name this process fills.

    Returns:
        (str) The declared component name.

    Raises:
        PortCanonError: If no row, or more than one, claims to be served here. Both are
            unrecoverable for the compare view: none leaves every binding unexplained, and two
            would make the answer depend on file order.
    """
    served = [row.component for row in load_port_canon() if row.served_by_this_process]
    if len(served) != 1:
        raise PortCanonError(
            f"{CANON_PATH} has {len(served)} rows marked {SERVED_HERE_FIELD}, expected exactly 1"
        )
    return served[0]


__all__ = [
    "CANON_PATH",
    "COMPONENTS_KEY",
    "SERVED_HERE_FIELD",
    "CanonPort",
    "PortCanonError",
    "load_port_canon",
    "served_component",
]
