"""Depth fill rate: the fraction of pixels carrying a real measurement (WP-3B-03).

`06` §2.4 / FR-CAM-040: a depth pixel of 0 mm means "no measurement available", so
the fill rate — the fraction of *non-zero* pixels — is the live quality signal the
depth preview displays, and its complement is the hole fraction the operator watches.

Fill rate is computed on the raw `(H, W, 1)` uint16 frame, before encoding: the lossy
log encoder (`encoding.py`) maps the 0 sentinel to `depth_min`, not back to 0, so the
holes do not survive quantisation and this measurement must be taken upstream of it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from backend.sensing.depth.constants import DEPTH_NO_MEASUREMENT_MM


@dataclass(frozen=True)
class FillRateReport:
    """The measured/hole split of one depth frame (FR-CAM-040).

    Attributes:
        total_pixels: Pixel count of the frame.
        measured_pixels: Pixels carrying a non-zero (measured) depth.
    """

    total_pixels: int
    measured_pixels: int

    @property
    def hole_pixels(self) -> int:
        """Pixels with no measurement (value 0)."""
        return self.total_pixels - self.measured_pixels

    @property
    def fill_rate(self) -> float:
        """Fraction of pixels carrying a measurement, in `[0, 1]`."""
        return self.measured_pixels / self.total_pixels

    @property
    def hole_fraction(self) -> float:
        """Fraction of no-measurement pixels, in `[0, 1]`."""
        return self.hole_pixels / self.total_pixels


def compute_fill_rate(depth_mm: NDArray[np.uint16]) -> FillRateReport:
    """Compute the fill rate of a depth frame (`06` §2.4, FR-CAM-040).

    Args:
        depth_mm: Depth in millimetres; 0 means no measurement.

    Returns:
        (FillRateReport) The measured/hole split of the frame.

    Raises:
        ValueError: If the frame is empty, so a fraction is undefined.
    """
    total = int(depth_mm.size)
    if total == 0:
        raise ValueError("an empty depth frame has no fill rate")
    measured = int(np.count_nonzero(depth_mm != DEPTH_NO_MEASUREMENT_MM))
    return FillRateReport(total_pixels=total, measured_pixels=measured)
