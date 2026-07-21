"""Active CAN double-bind check (WP-0B-04): no healthy report while a second binds.

`01` NFR-SYS-004 makes double-bind absence a *precondition* of reporting normal
operation — "silent success is failure". SocketCAN RAW has no exclusive bind
(`16` §10.1), so a second bind succeeds silently (`12` §2.9); the only honest
answer is to actively check for another binder before saying `is_connected=True`.

This package is that check and its two enforcement halves:

- Runtime gate — `ConnectionGate` returns True only after `DoubleBindCheck` finds
  no foreign binder. `LockBindProbe` (over the `WP-0B-01` lock) catches a
  *cooperating* binder and runs on any host; a live SocketCAN probe (`WP-0B-03`)
  catches a *non-cooperating* one and plugs in identically.
- Static ban — `find_banned_driver_import` rejects `openarm_driver` on the
  canonical path (`01` FR-SYS-010): it opens its own CAN socket, a double bind the
  flock cannot see, so it is stopped at import time, not at runtime.

`IntruderBindProbe` adapts WP-0B-03's TX-intruder faults into the same probe
interface, so a live second *writer* (invisible to the flock) gates the report too.

`driver_audit` renders the `16` M-24 verdict (does `openarm_driver` open CAN
in-process) from a reproducible source reading, and `reverify` re-runs the two
deferred checks (real `driver.py`, real second SocketCAN bind) against real input.
"""

from __future__ import annotations

from backend.can.bind.connection_gate import ConnectionGate
from backend.can.bind.double_bind import (
    BindProbe,
    DoubleBindCheck,
    DoubleBindError,
    ForeignBinder,
    LockBindProbe,
    StaticBindProbe,
)
from backend.can.bind.driver_audit import (
    CitedLine,
    M24Verdict,
    audit_driver_source,
    audit_installed_package,
    render_m24_row,
)
from backend.can.bind.intruder_probe import IntruderBindProbe
from backend.can.bind.staticcheck import (
    ALLOWED_MODULES,
    BANNED_DRIVER_MODULE,
    StaticViolation,
    find_banned_driver_import,
)

__all__ = [
    "ALLOWED_MODULES",
    "BANNED_DRIVER_MODULE",
    "BindProbe",
    "CitedLine",
    "ConnectionGate",
    "DoubleBindCheck",
    "DoubleBindError",
    "ForeignBinder",
    "IntruderBindProbe",
    "LockBindProbe",
    "M24Verdict",
    "StaticBindProbe",
    "StaticViolation",
    "audit_driver_source",
    "audit_installed_package",
    "find_banned_driver_import",
    "render_m24_row",
]
