"""Intermediate-storage disk budget correction (`02b` §6.2 WP-3B-05 ⑤).

The `15` NFR-PRF-026/028 disk budget and the `14` F14 record-block thresholds were
first written against a JPEG-q90 intermediate. The canonical two-stage intermediate
is a lossless PNG original (depth 16-bit TIFF), which is 3-8x larger (`06` §2.8), so
those thresholds are *invalid as written* and must be raised by a factor in that
band before they gate anything.

This module carries that correction. It exposes the band as the two named ratios,
turns a JPEG-q90 byte estimate into the PNG intermediate budget band, and measures
the real PNG/JPEG-q90 ratio of a frame so a caller can confirm the direction
(lossless is always the larger). The exact multiplier on real imagery is an M-5
real-fixture measurement (`15` NFR-PRF-026 note); on synthetic noise the ratio does
not land in [3, 8], so callers confirm direction here and defer the band figure.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from backend.sensing.encoding.constants import (
    JPEG_Q90_QUALITY,
    PNG_COMPRESSION_LEVEL,
    PNG_OVER_JPEG_Q90_MAX_RATIO,
    PNG_OVER_JPEG_Q90_MIN_RATIO,
)


@dataclass(frozen=True)
class IntermediateBudget:
    """A JPEG-q90 byte estimate corrected to the lossless-PNG intermediate band.

    Attributes:
        jpeg_q90_bytes: The original JPEG-q90 estimate the budget was written for.
        png_min_bytes: The lower edge of the corrected PNG budget (3x).
        png_max_bytes: The upper edge of the corrected PNG budget (8x).
    """

    jpeg_q90_bytes: float
    png_min_bytes: float
    png_max_bytes: float


def png_intermediate_budget(jpeg_q90_bytes: float) -> IntermediateBudget:
    """Correct a JPEG-q90 byte budget to the lossless-PNG intermediate band.

    The record-block threshold must be raised to at least the lower edge; the upper
    edge is the worst-case disk the operator must provision for (`15` NFR-PRF-028).

    Args:
        jpeg_q90_bytes: The JPEG-q90 byte estimate the legacy budget assumed.

    Returns:
        (IntermediateBudget) The estimate with its corrected PNG budget band.

    Raises:
        ValueError: If the estimate is negative.
    """
    if jpeg_q90_bytes < 0:
        raise ValueError(f"jpeg_q90_bytes must be >= 0, got {jpeg_q90_bytes}")
    return IntermediateBudget(
        jpeg_q90_bytes=jpeg_q90_bytes,
        png_min_bytes=jpeg_q90_bytes * PNG_OVER_JPEG_Q90_MIN_RATIO,
        png_max_bytes=jpeg_q90_bytes * PNG_OVER_JPEG_Q90_MAX_RATIO,
    )


def measured_png_jpeg_bytes(array: np.ndarray) -> tuple[int, int]:
    """Encode one RGB frame both ways and return the (PNG, JPEG-q90) byte lengths.

    A real measurement, not a coefficient: the lossless PNG is always the larger of
    the two, which is the direction acceptance ⑤ asserts. The absolute ratio depends
    on image content (noise inflates PNG well past 8x), so a caller checks the
    direction here and leaves the band figure to the real-imagery M-5 measurement.

    Args:
        array: An RGB frame array (`(H, W, 3)` uint8).

    Returns:
        (tuple[int, int]) `(png_bytes, jpeg_q90_bytes)`.

    Raises:
        ValueError: If either encode fails.
    """
    contiguous = np.ascontiguousarray(array)
    png_ok, png_buffer = cv2.imencode(
        ".png", contiguous, [cv2.IMWRITE_PNG_COMPRESSION, PNG_COMPRESSION_LEVEL]
    )
    jpeg_ok, jpeg_buffer = cv2.imencode(
        ".jpg", contiguous, [cv2.IMWRITE_JPEG_QUALITY, JPEG_Q90_QUALITY]
    )
    if not png_ok or not jpeg_ok:
        raise ValueError("failed to encode frame for PNG/JPEG budget comparison")
    return len(png_buffer), len(jpeg_buffer)
