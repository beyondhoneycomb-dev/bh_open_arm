"""WP-3B-03 — depth fill rate (FR-CAM-040), the measured/hole split of a frame.

The fill-rate *math* runs here on synthetic depth arrays; the live display on a real
RealSense stream is deferred (`test_reverify_hook`). A pixel of 0 is a hole; every
other value is measured.
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.sensing.depth.fill_rate import compute_fill_rate


def test_all_measured_is_full() -> None:
    """A frame with no zero pixel is fully filled."""
    depth = np.full((4, 5, 1), 1500, dtype=np.uint16)
    report = compute_fill_rate(depth)
    assert report.total_pixels == 20
    assert report.measured_pixels == 20
    assert report.hole_pixels == 0
    assert report.fill_rate == 1.0
    assert report.hole_fraction == 0.0


def test_all_holes_is_empty() -> None:
    """A frame of only no-measurement pixels has zero fill rate."""
    depth = np.zeros((4, 5, 1), dtype=np.uint16)
    report = compute_fill_rate(depth)
    assert report.measured_pixels == 0
    assert report.fill_rate == 0.0
    assert report.hole_fraction == 1.0


def test_mixed_frame_counts_zero_pixels_as_holes() -> None:
    """Exactly the zero pixels are holes; the rest are measured."""
    depth = np.full((2, 5, 1), 800, dtype=np.uint16)
    depth[0, 0, 0] = 0
    depth[1, 4, 0] = 0
    report = compute_fill_rate(depth)
    assert report.total_pixels == 10
    assert report.hole_pixels == 2
    assert report.measured_pixels == 8
    assert report.fill_rate == pytest.approx(0.8)
    assert report.hole_fraction == pytest.approx(0.2)


def test_empty_frame_has_no_fill_rate() -> None:
    """An empty frame raises rather than dividing by zero."""
    with pytest.raises(ValueError, match="empty depth frame"):
        compute_fill_rate(np.empty((0,), dtype=np.uint16))
