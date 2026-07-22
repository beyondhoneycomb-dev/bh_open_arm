"""Real-fixture re-verification hook for the deferred real-CAN acceptances (plan 02a §4.1).

Most of WP-1-04 runs on this host: the `PG-RT-001a` judge over the synthetic sweep,
the `PG-CAN-001` judge logic, the `f_max` arithmetic, and the session and publish
guards. What does not run here is every acceptance that needs a real CAN bus — the
on-hardware conditions 1-7 sweep, the real `candump` frames-per-cycle count, and the
`WP-0B-06` `f_max_can` — because there is no adapter, no motor and no vcan on this
host. Those are deferred, not asserted green and not dropped.

This is the hook the deferral is required to ship. The moment a directory of real
captures is supplied via `OPENARM_RTBENCH_REAL_FIXTURE`, `reverify_from_fixture`
re-runs the *identical* judges — `judge_pg_rt_001a` over the real band overrun and
`judge_pg_can_001` over the real `candump` count — against the real numbers. Until
then the bound tests skip with a reason. A capture is one JSON per host in the
`RealCapture` schema below; its frame count is judged as `REAL_CANDUMP`, never as a
model, so the hook can never manufacture the very bus number `THE ONE RULE` forbids.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.rtbench.fmax import FMax, compute_fmax
from backend.rtbench.frame_count import FrameCountSource, PgCan001Verdict, judge_pg_can_001
from backend.rtbench.judge import BandPoint, PgRt001aVerdict, judge_pg_rt_001a

# Environment variable a caller sets to point the hook at a real capture directory.
FIXTURE_ENV_VAR = "OPENARM_RTBENCH_REAL_FIXTURE"


@dataclass(frozen=True)
class RealVerification:
    """The verdicts a real capture produced, one per host file.

    Attributes:
        host_id: The control host the capture came from (`05` NFR-TEL-004).
        pg_rt_001a: The `PG-RT-001a` verdict over the real band overrun.
        pg_can_001: The `PG-CAN-001` verdict over the real `candump` count.
        fmax: `f_max = min(f_max_can, f_max_python)` with the real CAN bound present.
    """

    host_id: str
    pg_rt_001a: PgRt001aVerdict
    pg_can_001: PgCan001Verdict
    fmax: FMax


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


def _band_points(capture: dict[str, Any]) -> tuple[BandPoint, ...]:
    """Build band points from a real capture's `band_overrun` list.

    Args:
        capture: One parsed capture record.

    Returns:
        (tuple[BandPoint, ...]) The real (frequency, overrun-rate) sweep.
    """
    return tuple(
        BandPoint(target_hz=float(point["target_hz"]), overrun_rate=float(point["overrun_rate"]))
        for point in capture.get("band_overrun", [])
    )


def _verify_one(capture: dict[str, Any]) -> RealVerification:
    """Re-run the judges over one real capture record.

    Args:
        capture: One parsed capture record in the `RealCapture` schema.

    Returns:
        (RealVerification) The three verdicts derived from the real numbers.
    """
    pg_rt = judge_pg_rt_001a(_band_points(capture))
    pg_can = judge_pg_can_001(int(capture["frames_per_cycle"]), FrameCountSource.REAL_CANDUMP)
    fmax = compute_fmax(
        f_max_can_hz=capture.get("f_max_can_hz"),
        f_max_python_hz=capture.get("f_max_python_hz"),
    )
    return RealVerification(
        host_id=str(capture.get("host_id", "unknown")),
        pg_rt_001a=pg_rt,
        pg_can_001=pg_can,
        fmax=fmax,
    )


def reverify_from_fixture(fixture_dir: Path) -> list[RealVerification]:
    """Re-run the WP-1-04 judgments against real captured measurements.

    Loads every `*.json` capture in the directory and runs the identical
    `PG-RT-001a`/`PG-CAN-001`/`f_max` judgments the offline tests exercise, now pointed
    at real band overrun and a real `candump` count. This is the re-verification the
    deferred real-CAN acceptances require.

    Args:
        fixture_dir: Directory of captured measurement JSON files, one per host.

    Returns:
        (list[RealVerification]) One verification per capture file, ordered by filename.

    Raises:
        FileNotFoundError: If the directory holds no `*.json` capture.
    """
    capture_files = sorted(fixture_dir.glob("*.json"))
    if not capture_files:
        raise FileNotFoundError(f"no *.json rtbench capture in {fixture_dir}")
    verifications: list[RealVerification] = []
    for path in capture_files:
        capture = json.loads(path.read_text(encoding="utf-8"))
        verifications.append(_verify_one(capture))
    return verifications
