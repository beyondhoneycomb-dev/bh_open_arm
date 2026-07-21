"""Real-fixture re-verification hook (acceptance ⑥, plan 02a §4.1).

The listener and TX checks are pure text parsers, so acceptance ④ and ⑤ run fully
here against synthetic fixtures. What does not run here is the claim that those
parsers read *real* kernel and iproute2 output correctly — the plan is explicit
(02a §4.1) that a parser passing every synthetic fixture can still misread a real
adapter's format, and that this risk is deferred, not removed.

This is the hook the deferral is required to ship: the moment a directory of real
captured output is supplied, `reverify_from_fixture` re-runs the *identical* checks
against the real bytes and compares the WARN/FAULT verdicts to what the capture
recorded. Until then the bound test skips with a reason. The fixture directory holds:

- ``rcvlist_all.txt``    — captured ``cat /proc/net/can/rcvlist_all``
- ``ip_s_link.txt``      — captured ``ip -s link show <iface>``
- ``expected.json``      — ``{iface, expected_own_listeners, backend_sent_frames,
  baseline_tx, expect_listener_warning, expect_tx_fault}``

so the same code path proves itself on real output without any hardware present at
authoring time.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.can.intruder.listener import RxListenerCheck
from backend.can.intruder.signals import ListenerWarning, TxMismatchFault
from backend.can.intruder.txwatch import TxCounterWatchdog

# Environment variable a caller sets to point the hook at a real capture directory.
FIXTURE_ENV_VAR = "OPENARM_INTRUDER_REAL_FIXTURE"
RCVLIST_FILENAME = "rcvlist_all.txt"
IP_STATS_FILENAME = "ip_s_link.txt"
EXPECTED_FILENAME = "expected.json"


@dataclass(frozen=True)
class ReverifyResult:
    """Outcome of re-verifying one real capture against its recorded expectation.

    Attributes:
        iface: Interface the capture covers.
        warning: The listener warning the RX check produced on the real bytes.
        fault: The TX-mismatch fault the watchdog produced on the real bytes.
        matched: True when both verdicts matched the recorded expectation.
        detail: Human-readable mismatch detail, empty on a match.
    """

    iface: str
    warning: ListenerWarning | None
    fault: TxMismatchFault | None
    matched: bool
    detail: str


def fixture_dir_from_env() -> Path | None:
    """Return the real-fixture directory named by the environment, if set and present.

    Returns:
        (Path | None) The directory, or None when unset or absent.
    """
    raw = os.environ.get(FIXTURE_ENV_VAR)
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_dir() else None


def reverify_from_fixture(fixture_dir: Path) -> ReverifyResult:
    """Re-run the listener and TX checks against a directory of real captures.

    Runs the same `RxListenerCheck` and `TxCounterWatchdog` the live path uses,
    pointed at the captured bytes, and checks their WARN/FAULT verdicts against the
    expectation the capture recorded. This is the identical logic the synthetic tests
    exercise, on real output.

    Args:
        fixture_dir: Directory holding the two captures plus ``expected.json``.

    Returns:
        (ReverifyResult) The re-verification outcome for the captured interface.

    Raises:
        FileNotFoundError: If any of the three required files is missing.
    """
    expected = _load_expected(fixture_dir)
    rcvlist_text = _read_required(fixture_dir / RCVLIST_FILENAME)
    ip_stats_text = _read_required(fixture_dir / IP_STATS_FILENAME)

    iface = str(expected["iface"])
    listener_check = RxListenerCheck(iface, int(expected["expected_own_listeners"]))
    tx_watchdog = TxCounterWatchdog(iface, int(expected["baseline_tx"]))

    warning = listener_check.evaluate_rcvlist(rcvlist_text)
    fault = tx_watchdog.evaluate_ip_stats(ip_stats_text, int(expected["backend_sent_frames"]))
    return _compare(iface, warning, fault, expected)


def _load_expected(fixture_dir: Path) -> dict[str, Any]:
    """Read and parse the expectation file, raising if it is absent."""
    expected_path = fixture_dir / EXPECTED_FILENAME
    if not expected_path.is_file():
        raise FileNotFoundError(f"missing {EXPECTED_FILENAME} in {fixture_dir}")
    parsed: dict[str, Any] = json.loads(expected_path.read_text(encoding="utf-8"))
    return parsed


def _read_required(path: Path) -> str:
    """Read a required capture file, raising a clear error when it is absent."""
    if not path.is_file():
        raise FileNotFoundError(f"missing {path.name} in {path.parent}")
    return path.read_text(encoding="utf-8")


def _compare(
    iface: str,
    warning: ListenerWarning | None,
    fault: TxMismatchFault | None,
    expected: dict[str, Any],
) -> ReverifyResult:
    """Compare produced verdicts against the recorded expectation."""
    mismatches: list[str] = []
    if (warning is not None) != bool(expected["expect_listener_warning"]):
        mismatches.append(
            f"listener warning {warning is not None} != {bool(expected['expect_listener_warning'])}"
        )
    if (fault is not None) != bool(expected["expect_tx_fault"]):
        mismatches.append(f"tx fault {fault is not None} != {bool(expected['expect_tx_fault'])}")
    return ReverifyResult(
        iface=iface,
        warning=warning,
        fault=fault,
        matched=not mismatches,
        detail="; ".join(mismatches),
    )
