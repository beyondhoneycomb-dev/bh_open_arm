"""The drop-rate computer (`06` NFR-CAM-003) and frame-number continuity (§2.6c).

The computer runs fully on synthetic counts and frame-number sequences here; only the
*real* drop measurement (a real 10-minute capture) is deferred, and that path is
re-run by the reverify hook. `02a` WP-0B-08 ⑥ defines the rate as `missing / expected`
with `expected = target_fps × duration`, which is exactly what is asserted.
"""

from __future__ import annotations

import pytest

from backend.camera import fixtures
from backend.camera.droprate import (
    compute_drop,
    expected_frame_count,
    frame_number_continuity,
)


def test_expected_count_is_fps_times_duration() -> None:
    """30 fps × 600 s = 18000 expected frames (NFR-CAM-003 formula)."""
    assert expected_frame_count(30, 600) == 18000


def test_drop_fraction_is_missing_over_expected() -> None:
    """297 of 300 expected received → 1% drop, in the 'ok' band."""
    report = compute_drop(target_fps=30, duration_s=10, received_count=297)
    assert report.expected == 300
    assert report.dropped == 3
    assert report.drop_fraction == pytest.approx(0.01)
    assert report.band == "ok"


def test_bands_classify_against_reference_thresholds() -> None:
    """> 2% warns, > 5% is a discard candidate (NFR-CAM-003 reference bands)."""
    warn = compute_drop(target_fps=30, duration_s=10, received_count=291)  # 3% dropped
    discard = compute_drop(target_fps=30, duration_s=10, received_count=282)  # 6% dropped
    assert warn.band == "warn"
    assert discard.band == "discard"


def test_frame_number_continuity_finds_gaps_and_duplicates() -> None:
    """The known fixture stream is missing {3, 7} and duplicates {5} (§2.6c)."""
    missing, duplicates = frame_number_continuity(fixtures.frame_numbers_with_drops())
    assert missing == (3, 7)
    assert duplicates == (5,)


def test_continuity_surfaces_gaps_the_raw_count_would_hide() -> None:
    """Frame-numbers can show a gap even when the received count looks complete.

    A stream that received the expected number of frames but whose device frame-numbers
    skip one has a real loss the count alone misses — the reason §2.6c wants both.
    """
    frame_numbers = [0, 1, 3, 4, 5]  # 5 frames received, but number 2 is missing
    report = compute_drop(
        target_fps=30, duration_s=5 / 30, received_count=5, frame_numbers=frame_numbers
    )
    assert report.dropped == 0
    assert report.missing_frame_numbers == (2,)


def test_zero_fps_is_rejected() -> None:
    """A zero target makes 'expected' meaningless — an error, not a divide-by-zero."""
    with pytest.raises(ValueError, match="positive"):
        expected_frame_count(0, 10)
