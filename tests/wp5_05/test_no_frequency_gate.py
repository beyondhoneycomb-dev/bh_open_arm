"""NORM-008 `ci_static` over `backend/loadtest`: the WS load test judges no frequency.

This tree is already clean, so the first test is a regression lock rather than a
discovery — it cannot have failed first. A lock over an absence goes green for two
different reasons, "nothing to find" and "the finder is broken", so the second test scans
a module written on the spot that definitely contains a banned shape. If the scanner ever
degrades to returning nothing, that one goes red and the lock's green stops meaning
anything.

The 30/60 Hz publish cap in `publish_rate.py` is deliberately not in scope: NFR-GUI-003 is
confirmed and appears nowhere in the ledger, and a bandwidth cap on a *request* is not a
measured loop rate being judged against a target, which is what NORM-008 is about.
"""

from __future__ import annotations

from pathlib import Path

import backend.loadtest.publish_rate as publish_rate_module
from backend.rtbench.staticcheck import SINK_RAISE, scan_frequency_verdicts

_LOADTEST_ROOT = Path(publish_rate_module.__file__).resolve().parent

_BANNED_SHAPE_SOURCE = '''"""A frequency bar guarding a raise — the shape the scan must report."""

CAP_HZ = 60.0


def refuse_above_cap(target_hz: float) -> None:
    if target_hz > CAP_HZ:
        raise ValueError(f"{target_hz} Hz is above the cap")
'''


def test_loadtest_has_no_frequency_verdict_path() -> None:
    sites = scan_frequency_verdicts((_LOADTEST_ROOT,))
    assert sites == [], "frequency values drive a verdict here:\n" + "\n".join(
        str(site) for site in sites
    )


def test_scanner_is_live_on_this_root(tmp_path: Path) -> None:
    (tmp_path / "banned_shape.py").write_text(_BANNED_SHAPE_SOURCE, encoding="utf-8")
    sites = scan_frequency_verdicts((tmp_path,))
    assert [site.sink for site in sites] == [SINK_RAISE]
    assert sites[0].symbol == "target_hz"
