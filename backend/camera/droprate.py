"""Frame-drop computer — expected vs received, plus frame-number continuity.

`02a` WP-0B-08 ⑥ and `06` NFR-CAM-003 define the drop rate as `frames-missing /
frames-expected`, where `expected = target_fps × duration`. That count-based figure
is one half; `06` §2.6c requires the other: device frame-numbers must be checked for
continuity, so a gap (a missing number) and a duplicate are surfaced independently of
the raw count. The two are reconciled in one report — a count that says "all present"
while frame-numbers show a gap is itself a finding.

The classification bands (warn / discard) are the NFR-CAM-003 reference fractions; a
band label is informational, not a gate that passes or fails here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from backend.camera.constants import DROP_DISCARD_FRACTION, DROP_WARN_FRACTION


def expected_frame_count(target_fps: float, duration_s: float) -> int:
    """Return `round(target_fps × duration)` — the NFR-CAM-003 expected-frame count."""
    if target_fps <= 0 or duration_s <= 0:
        raise ValueError("target_fps and duration_s must be positive")
    return round(target_fps * duration_s)


def frame_number_continuity(
    frame_numbers: Sequence[int],
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Return the missing and duplicated device frame-numbers (`06` §2.6c).

    Missing numbers are the integers skipped between consecutive received numbers;
    duplicates are frame-numbers that arrived more than once. Both are derived from
    the device-assigned sequence, independent of the raw received count.

    Args:
        frame_numbers: Device frame-numbers in arrival order.

    Returns:
        (tuple[tuple[int, ...], tuple[int, ...]]) `(missing, duplicated)`, each sorted.
    """
    seen: set[int] = set()
    duplicates: set[int] = set()
    for number in frame_numbers:
        if number in seen:
            duplicates.add(number)
        seen.add(number)

    missing: set[int] = set()
    ordered = sorted(seen)
    for low, high in zip(ordered, ordered[1:], strict=False):
        missing.update(range(low + 1, high))
    return tuple(sorted(missing)), tuple(sorted(duplicates))


@dataclass(frozen=True)
class DropReport:
    """One slot's drop outcome over a capture window.

    Attributes:
        expected: `round(target_fps × duration)`.
        received: Frames actually recorded.
        dropped: `max(expected - received, 0)`.
        drop_fraction: `dropped / expected`.
        missing_frame_numbers: Device frame-numbers skipped (empty when unknown).
        duplicate_frame_numbers: Device frame-numbers seen twice.
        band: Reference classification — "ok", "warn", or "discard".
    """

    expected: int
    received: int
    dropped: int
    drop_fraction: float
    missing_frame_numbers: tuple[int, ...]
    duplicate_frame_numbers: tuple[int, ...]
    band: str


def _band_for(drop_fraction: float) -> str:
    """Classify a drop fraction against the NFR-CAM-003 reference bands."""
    if drop_fraction > DROP_DISCARD_FRACTION:
        return "discard"
    if drop_fraction > DROP_WARN_FRACTION:
        return "warn"
    return "ok"


def compute_drop(
    target_fps: float,
    duration_s: float,
    received_count: int,
    frame_numbers: Sequence[int] | None = None,
) -> DropReport:
    """Compute the drop report for one slot.

    Args:
        target_fps: Target frames per second.
        duration_s: Capture window length in seconds.
        received_count: Frames actually recorded.
        frame_numbers: Optional device frame-number sequence for continuity.

    Returns:
        (DropReport) Count-based drop plus frame-number continuity.
    """
    if received_count < 0:
        raise ValueError("received_count cannot be negative")
    expected = expected_frame_count(target_fps, duration_s)
    dropped = max(expected - received_count, 0)
    drop_fraction = dropped / expected
    missing, duplicates = (
        frame_number_continuity(frame_numbers) if frame_numbers is not None else ((), ())
    )
    return DropReport(
        expected=expected,
        received=received_count,
        dropped=dropped,
        drop_fraction=drop_fraction,
        missing_frame_numbers=missing,
        duplicate_frame_numbers=duplicates,
        band=_band_for(drop_fraction),
    )
