"""Real-source / real-capture re-verification hooks (acceptance ⑤, plan 02a §4.1).

Two claims in this WP cannot be settled on this host and are deferred, not faked
green:

- The M-24 source reading (`driver_audit`) needs the real `openarm_driver`,
  which is not installed here. `reverify_driver_audit` re-runs the identical scan
  against a real `driver.py` the moment its path is supplied via
  `OPENARM_DRIVER_SOURCE`.
- The live double-bind gate against a real *non-cooperating* SocketCAN binder (a
  second python-can writer / `candump`) needs a real or virtual CAN interface,
  which this host lacks. `reverify_gate_from_capture` replays foreign-binder
  records captured from a real rig (or the `WP-0B-03` live probe) through the
  same gate and confirms it still refuses `is_connected`.

Until a fixture is supplied each hook returns None so the bound test skips with a
reason. The *cooperating*-binder half of the gate is not deferred: it is verified
here with a real second process holding the flock (`WP-0B-01` harness).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from backend.can.bind.connection_gate import ConnectionGate
from backend.can.bind.double_bind import (
    SOURCE_REPLAY,
    DoubleBindCheck,
    ForeignBinder,
    StaticBindProbe,
)
from backend.can.bind.driver_audit import M24Verdict, audit_driver_source

# Environment variable pointing at a real `openarm_driver/driver.py` for the M-24
# source reading; and at a directory of foreign-binder records captured from a real
# rig for the live-gate replay.
DRIVER_SOURCE_ENV_VAR = "OPENARM_DRIVER_SOURCE"
CAPTURE_ENV_VAR = "OPENARM_BIND_REAL_FIXTURE"
CAPTURE_FILENAME = "foreign_binders.json"


def driver_source_from_env() -> Path | None:
    """Return the real `driver.py` named by the environment, if set and present.

    Returns:
        (Path | None) The file, or None when unset or absent.
    """
    raw = os.environ.get(DRIVER_SOURCE_ENV_VAR)
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_file() else None


def reverify_driver_audit(source: Path) -> M24Verdict:
    """Re-run the M-24 source reading against a real `driver.py`.

    This is the identical scan the synthetic tests run, pointed at real bytes, so
    a real `openarm_driver` produces a line-cited verdict the moment it is present.

    Args:
        source: Path to the real `driver.py`.

    Returns:
        (M24Verdict) The read judgment.
    """
    return audit_driver_source(source)


def capture_dir_from_env() -> Path | None:
    """Return the real-capture directory named by the environment, if present.

    Returns:
        (Path | None) The directory, or None when unset or absent.
    """
    raw = os.environ.get(CAPTURE_ENV_VAR)
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_dir() else None


def load_captured_binders(capture_dir: Path) -> tuple[ForeignBinder, ...]:
    """Load foreign-binder records captured from a real rig.

    The capture is a JSON array of `{iface, source?, detail?, holder_pid?}`
    objects — the shape a real `WP-0B-03` live probe (or a manual candump/second-
    writer capture) records when a second bind is present.

    Args:
        capture_dir: Directory holding `foreign_binders.json`.

    Returns:
        (tuple[ForeignBinder, ...]) The captured binders.

    Raises:
        FileNotFoundError: If the capture file is missing from the directory.
    """
    capture = capture_dir / CAPTURE_FILENAME
    if not capture.is_file():
        raise FileNotFoundError(f"missing {CAPTURE_FILENAME} in {capture_dir}")
    records = json.loads(capture.read_text(encoding="utf-8"))
    return tuple(
        ForeignBinder(
            iface=str(record["iface"]),
            source=str(record.get("source", SOURCE_REPLAY)),
            detail=str(record.get("detail", "captured foreign binder")),
            holder_pid=record.get("holder_pid"),
        )
        for record in records
    )


def reverify_gate_from_capture(capture_dir: Path) -> bool:
    """Replay captured foreign binders through the gate and return its is_connected.

    Feeds a real rig's captured binders through the identical `ConnectionGate`
    the live path uses, with a transport that reports up, so the caller can assert
    the gate still refuses (`False`) despite the transport being healthy — the
    silent-success failure NFR-SYS-004 forbids.

    Args:
        capture_dir: Directory holding the captured binder records.

    Returns:
        (bool) The gate's `is_connected` verdict over the captured binders — False
        whenever the capture names a binder on a probed interface.
    """
    binders = load_captured_binders(capture_dir)
    ifaces = sorted({binder.iface for binder in binders})
    gate = ConnectionGate(DoubleBindCheck([StaticBindProbe(binders)]))
    return gate.is_connected(ifaces, _transport_up)


def _transport_up() -> bool:
    """Transport probe that always reports connected, isolating the gate's decision."""
    return True
