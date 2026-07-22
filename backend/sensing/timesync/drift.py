"""Session-drift check: compare a slot pair's q99 slop at session start vs end.

`02b` §6.2 WP-3B-04 ④ asks whether the clocks drift over a session — confirmed by
comparing each slot pair's q99 capture-timestamp difference in an early window
against a late window. A q99 that grew means the pair drifted apart.

The distribution itself — the nearest-match difference, its quantiles and the
required histogram — is not recomputed here: it is the frozen `backend.camera.syncslop`
computer (`02a` WP-0B-08 ⑤), imported and reused so the slop math has one home. This
module only windows a session and diffs the two q99 values, so a second slop
definition never appears.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from backend.camera.syncslop import SyncSlopReport, build_slop_reports


@dataclass(frozen=True)
class DriftReport:
    """How one slot pair's q99 slop changed across a session.

    Attributes:
        pair: The two slot keys, sorted.
        start_q99_ms: The pair's q99 difference in the early window.
        end_q99_ms: The pair's q99 difference in the late window.
        delta_q99_ms: `end - start`; positive means the pair drifted apart.
    """

    pair: tuple[str, str]
    start_q99_ms: float
    end_q99_ms: float
    delta_q99_ms: float

    def drifted(self, tolerance_ms: float) -> bool:
        """Whether the q99 grew by more than a tolerance across the session.

        Args:
            tolerance_ms: The largest q99 growth treated as steady, in milliseconds.

        Returns:
            (bool) True when `delta_q99_ms` exceeds the tolerance.
        """
        return self.delta_q99_ms > tolerance_ms


def session_drift(
    start_streams: Mapping[str, Sequence[int]],
    end_streams: Mapping[str, Sequence[int]],
) -> list[DriftReport]:
    """Compare per-pair q99 slop between a session's start and end windows.

    Both windows must carry the same slot pairs — drift is a property of a pair, so a
    pair present in only one window has nothing to compare against.

    Args:
        start_streams: Slot to capture_ts (ns) for the early window (>= two slots).
        end_streams: Slot to capture_ts (ns) for the late window, same slots.

    Returns:
        (list[DriftReport]) One report per slot pair, in pair order.

    Raises:
        ValueError: If the two windows do not cover the same slot pairs.
    """
    start_reports: dict[tuple[str, str], SyncSlopReport] = {
        report.pair: report for report in build_slop_reports(start_streams)
    }
    end_reports: dict[tuple[str, str], SyncSlopReport] = {
        report.pair: report for report in build_slop_reports(end_streams)
    }
    if set(start_reports) != set(end_reports):
        raise ValueError("start and end windows must cover the same slot pairs to measure drift")
    reports: list[DriftReport] = []
    for pair in sorted(start_reports):
        start_q99 = start_reports[pair].q99_ms
        end_q99 = end_reports[pair].q99_ms
        reports.append(
            DriftReport(
                pair=pair,
                start_q99_ms=start_q99,
                end_q99_ms=end_q99,
                delta_q99_ms=end_q99 - start_q99,
            )
        )
    return reports
