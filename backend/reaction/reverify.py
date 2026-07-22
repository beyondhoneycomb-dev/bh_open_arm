"""Deferred real-fixture re-verification of the hold send period (`NFR-SAF-007`).

Almost all of WP-2C-05 runs on this host: the six strategies, the three guards, the
policy contract, the latch reuse, and the continuous-send proof on the fake writer.
What cannot run here is the *quantitative* `NFR-SAF-007` acceptance — that the Cat-2
hold's CAN send period stays below the RID-9 `TIMEOUT`. The RID-9 factory `TIMEOUT` is
`[결정필요]` (unread without the CAN bus), and the true send period needs a hardware
candump timestamp, so the number is deferred rather than asserted green (`THE ONE
RULE`).

This is the hook the deferral ships. When a directory of real candump captures is named
by `OPENARM_REACTION_REAL_FIXTURE`, `reverify_from_fixture` re-applies the identical
check — max inter-send interval strictly below the measured RID-9 timeout — against the
real send timestamps. Both numbers come from the capture (the measured send times and
the register-read timeout), so the hook cannot manufacture a pass: a capture whose gap
reaches the timeout fails exactly as it must.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.reaction.constants import FIXTURE_ENV_VAR


@dataclass(frozen=True)
class HoldSendPeriodVerification:
    """The verdict one real hold-send capture produced (`NFR-SAF-007`).

    Attributes:
        source: The capture file name.
        max_interval_sec: The largest gap between consecutive hold sends.
        rid9_timeout_sec: The RID-9 `TIMEOUT` read from the motor for this capture.
        within_deadline: Whether every send gap stayed strictly below the timeout.
    """

    source: str
    max_interval_sec: float
    rid9_timeout_sec: float
    within_deadline: bool


def fixture_dir_from_env() -> Path | None:
    """Return the real-fixture directory named by the environment, if set and present.

    Returns:
        (Path | None) The directory, or None when unset or absent — the offline case,
        where the hold-send-period acceptance is skipped-with-reason.
    """
    raw = os.environ.get(FIXTURE_ENV_VAR)
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_dir() else None


def _max_interval(timestamps: list[float]) -> float:
    """Return the largest gap between consecutive send timestamps.

    Args:
        timestamps: Monotonic send timestamps, seconds; needs at least two.

    Returns:
        (float) The maximum consecutive interval.

    Raises:
        ValueError: If fewer than two timestamps are given (no interval to measure).
    """
    if len(timestamps) < 2:
        raise ValueError("a hold-send capture needs at least two timestamps to measure an interval")
    ordered = sorted(timestamps)
    return max(later - earlier for earlier, later in zip(ordered, ordered[1:], strict=False))


def _verify_one(source: str, capture: dict[str, Any]) -> HoldSendPeriodVerification:
    """Re-apply the `NFR-SAF-007` deadline check to one real capture.

    Args:
        source: The capture file name, for the verdict.
        capture: One parsed capture with send timestamps and the RID-9 timeout.

    Returns:
        (HoldSendPeriodVerification) The verdict; `within_deadline` false when a gap
        reached the timeout.
    """
    timestamps = [float(value) for value in capture["send_timestamps_sec"]]
    rid9_timeout_sec = float(capture["rid9_timeout_sec"])
    max_interval_sec = _max_interval(timestamps)
    return HoldSendPeriodVerification(
        source=source,
        max_interval_sec=max_interval_sec,
        rid9_timeout_sec=rid9_timeout_sec,
        within_deadline=max_interval_sec < rid9_timeout_sec,
    )


def reverify_from_fixture(fixture_dir: Path) -> list[HoldSendPeriodVerification]:
    """Re-run the hold-send-period deadline check against real candump captures.

    Args:
        fixture_dir: Directory of captured candump JSON files.

    Returns:
        (list[HoldSendPeriodVerification]) One verification per capture, by filename.

    Raises:
        FileNotFoundError: If the directory holds no `*.json` capture.
    """
    capture_files = sorted(fixture_dir.glob("*.json"))
    if not capture_files:
        raise FileNotFoundError(f"no *.json hold-send capture in {fixture_dir}")
    return [
        _verify_one(path.name, json.loads(path.read_text(encoding="utf-8")))
        for path in capture_files
    ]
