"""WP-3B-05 ⑤ — the disk budget reflects that lossless PNG is 3-8x JPEG q90.

The `15` NFR-PRF-026/028 budget and the `14` F14 record-block thresholds were
written for a JPEG-q90 intermediate; the canonical intermediate is a lossless PNG
original, 3-8x larger (`06` §2.8), so those figures must be raised by a factor in
that band. These prove the correction is applied and that a real encode confirms the
direction (lossless is the larger); the exact multiplier on real imagery is the M-5
real-fixture measurement, so the band figure is not asserted on synthetic noise.
"""

from __future__ import annotations

import pytest

from backend.sensing.encoding import (
    PNG_OVER_JPEG_Q90_MAX_RATIO,
    PNG_OVER_JPEG_Q90_MIN_RATIO,
    measured_png_jpeg_bytes,
    png_intermediate_budget,
)
from tests.wp3b05.support import frame_array, rgb_camera


def test_budget_band_is_three_to_eight():
    """The correction band is the spec's 3-8x lossless-PNG-over-JPEG-q90 figure."""
    assert PNG_OVER_JPEG_Q90_MIN_RATIO == 3.0
    assert PNG_OVER_JPEG_Q90_MAX_RATIO == 8.0


def test_png_budget_inflates_jpeg_estimate_into_the_band():
    """A JPEG-q90 byte estimate is corrected to the 3x..8x PNG intermediate band."""
    budget = png_intermediate_budget(1000.0)
    assert budget.png_min_bytes == 3000.0
    assert budget.png_max_bytes == 8000.0
    assert budget.png_min_bytes > budget.jpeg_q90_bytes


def test_negative_estimate_is_refused():
    """A negative byte estimate is not a budget."""
    with pytest.raises(ValueError, match="jpeg_q90_bytes"):
        png_intermediate_budget(-1.0)


def test_measured_png_is_larger_than_jpeg_q90():
    """A real encode confirms the direction: the lossless original is the larger.

    At a realistic resolution the lossless PNG is unambiguously larger than JPEG q90
    (the fixture's textured frame encodes to several times the JPEG size). Only the
    *direction* is asserted here — the exact 3-8x band is a real-imagery figure whose
    point measurement is deferred to the M-5 real-fixture run (`15` NFR-PRF-026), and
    a 16px tile would be dominated by container overhead, so a realistic size is used.
    """
    frame = rgb_camera(width=128, height=128).read(0)
    assert frame is not None
    png_bytes, jpeg_bytes = measured_png_jpeg_bytes(frame_array(frame))
    assert png_bytes > jpeg_bytes
