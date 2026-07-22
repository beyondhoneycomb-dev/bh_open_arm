"""Re-verification hook: re-run the slop/drift checks over a real capture fixture.

The nearest-match, drop and same-fps logic all run here against the synthetic-jitter
fixture and genuinely pass. What cannot run here is the *physical* sync slop of real
RealSense cameras and the hardware-sync 3.3 ms target — that figure is `[미확인]`
until real cameras are observed (`02b` §6.2 WP-3B-04, `PG-CAM-001`). This hook is the
machinery that re-runs the slop-drift verification the moment a real capture is
supplied: it reloads a session's early/late `capture_ts` windows, recomputes each
pair's q99 drift through the same `session_drift` path, and checks them against a
recorded bound.

Following `02a` §4.1 and the CTR-CAP twin (`contracts.capture.reverify`), the
real-device leg is deferred behind `OPENARM_TIMESYNC_REAL_FIXTURE`, unset in this
environment, so the real-hardware test skips rather than asserting a fabricated slop.
The machinery itself is exercised offline against a planted fixture directory.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from backend.sensing.timesync.drift import DriftReport, session_drift

# The environment variable naming a real-device capture fixture directory. Unset in
# the offline environment, which is why the real-hardware test skips.
REAL_FIXTURE_ENV = "OPENARM_TIMESYNC_REAL_FIXTURE"

# The two files a fixture directory holds: the session's start/end capture_ts windows
# and the bound the recomputed drift is checked against.
SESSION_FILE = "session.json"
EXPECTED_FILE = "expected.json"


@dataclass(frozen=True)
class DriftVerifyResult:
    """The outcome of re-verifying one slot pair's drift against its bound.

    Attributes:
        pair: The slot pair re-verified.
        report: The recomputed drift report.
        matched: Whether the recomputed q99 and drift stayed within the bounds.
        detail: A human-readable description of a breach, empty when matched.
    """

    pair: tuple[str, str]
    report: DriftReport
    matched: bool
    detail: str


def fixture_dir_from_env() -> Path | None:
    """Return the real-device fixture directory, when one is configured.

    Returns:
        (Path | None) The directory `OPENARM_TIMESYNC_REAL_FIXTURE` names, or None.
    """
    value = os.environ.get(REAL_FIXTURE_ENV)
    return Path(value) if value else None


def reverify_from_fixture(fixture_dir: Path) -> list[DriftVerifyResult]:
    """Re-run the session-drift check over one fixture directory.

    Reloads the session's early and late `capture_ts` windows, recomputes per-pair
    q99 drift through `session_drift`, and checks each pair's late-window q99 and its
    drift against the recorded bounds.

    Args:
        fixture_dir: A directory holding `session.json` and `expected.json`.

    Returns:
        (list[DriftVerifyResult]) One result per slot pair, in pair order.

    Raises:
        FileNotFoundError: If either fixture file is absent.
    """
    session = json.loads((fixture_dir / SESSION_FILE).read_text(encoding="utf-8"))
    expected = json.loads((fixture_dir / EXPECTED_FILE).read_text(encoding="utf-8"))

    max_end_q99_ms = expected["max_end_q99_ms"]
    max_drift_ms = expected["max_drift_ms"]

    results: list[DriftVerifyResult] = []
    for report in session_drift(session["start"], session["end"]):
        breach = []
        if report.end_q99_ms > max_end_q99_ms:
            breach.append(f"end q99 {report.end_q99_ms:.3f} ms exceeds bound {max_end_q99_ms} ms")
        if report.delta_q99_ms > max_drift_ms:
            breach.append(f"drift {report.delta_q99_ms:.3f} ms exceeds bound {max_drift_ms} ms")
        results.append(
            DriftVerifyResult(
                pair=report.pair,
                report=report,
                matched=not breach,
                detail="; ".join(breach),
            )
        )
    return results
