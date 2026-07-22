"""Depth quantisation parameters and the round-trip encode/decode (WP-3B-03).

`06` §2.4 fixes the depth encoder as LeRobot v0.6.0's `DepthEncoderConfig`: a 12-bit
logarithmic quantisation with per-camera `depth_min`/`depth_max`/`shift`/`use_log`
(FR-CAM-039). The quantisation *math* is the frozen upstream — this module holds the
parameters per camera and delegates the transform to `lerobot.datasets.depth_utils`,
so there is exactly one implementation of the encoder grid. Reimplementing the formula
here would be a second source of truth for `06` §2.4.

`lerobot` pulls the training stack (torch, av); it is imported at call time, not at
module load, so importing the camera path does not drag that stack into every
consumer, and the upstream defaults are read through `default_depth_encoding_params`
rather than frozen into a field default at import time.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


class DepthEncodingError(ValueError):
    """Raised when depth encoding parameters cannot define a valid quantiser."""


@dataclass(frozen=True)
class DepthEncodingParams:
    """One camera's depth quantiser settings (FR-CAM-039).

    `depth_min`, `depth_max` and `shift` are in metres, matching the upstream
    `DepthEncoderConfig`; the input depth frames this encodes are uint16 millimetres,
    and the unit conversion lives inside the delegated transform.

    Attributes:
        depth_min: Depth (metres) mapped to quantum 0.
        depth_max: Depth (metres) mapped to the top quantum.
        shift: Pre-log offset (metres); log mode requires `depth_min + shift > 0`.
        use_log: Quantise in log space (True) or linearly (False).
    """

    depth_min: float
    depth_max: float
    shift: float
    use_log: bool

    def __post_init__(self) -> None:
        """Reject a range or shift that cannot define an invertible quantiser."""
        if self.depth_min >= self.depth_max:
            raise DepthEncodingError(
                f"depth_min ({self.depth_min}) must be below depth_max ({self.depth_max})"
            )
        if self.use_log and self.depth_min + self.shift <= 0:
            raise DepthEncodingError(
                f"log quantisation needs depth_min + shift > 0, got "
                f"{self.depth_min} + {self.shift} = {self.depth_min + self.shift}"
            )

    def encode(self, depth_mm: NDArray[np.uint16]) -> NDArray[np.uint16]:
        """Quantise an `(H, W, 1)` uint16 mm depth frame to 12-bit codes.

        Args:
            depth_mm: Depth in millimetres; 0 means no measurement.

        Returns:
            (NDArray[np.uint16]) 12-bit codes, shape `(H, W)`, values `0..DEPTH_QMAX`.
        """
        from lerobot.configs.video import DEPTH_MILLIMETER_UNIT
        from lerobot.datasets.depth_utils import quantize_depth

        codes = quantize_depth(
            depth_mm,
            depth_min=self.depth_min,
            depth_max=self.depth_max,
            shift=self.shift,
            use_log=self.use_log,
            video_backend=None,
            input_unit=DEPTH_MILLIMETER_UNIT,
        )
        return np.asarray(codes, dtype=np.uint16)

    def decode(self, codes: NDArray[np.uint16]) -> NDArray[np.uint16]:
        """Invert `encode`, returning an `(H, W, 1)` uint16 mm depth frame.

        Tuning arguments match `encode`, so the pair round-trips a valid depth to
        within the quantiser's resolution. The 0 = no-measurement sentinel is *not*
        recovered — the lossy grid maps it to `depth_min` — so the invalid mask must
        be carried alongside (see `fill_rate`).

        Args:
            codes: 12-bit codes produced by `encode`.

        Returns:
            (NDArray[np.uint16]) Depth in millimetres, shape `(H, W, 1)`.
        """
        from lerobot.configs.video import DEPTH_MILLIMETER_UNIT
        from lerobot.datasets.depth_utils import dequantize_depth

        depth_mm = dequantize_depth(
            codes,
            depth_min=self.depth_min,
            depth_max=self.depth_max,
            shift=self.shift,
            use_log=self.use_log,
            output_unit=DEPTH_MILLIMETER_UNIT,
            output_tensor=False,
            output_channel_last=True,
        )
        return np.asarray(depth_mm, dtype=np.uint16)


def default_depth_encoding_params(
    depth_min: float | None = None,
    depth_max: float | None = None,
    shift: float | None = None,
    use_log: bool | None = None,
) -> DepthEncodingParams:
    """Build the common-default depth parameters, with optional per-camera overrides.

    The defaults are LeRobot v0.6.0's `DEFAULT_DEPTH_*` constants (`06` §2.4:
    `[0.01, 10.0] m`, `shift 3.5`, log on), read from the upstream rather than
    restated. A near-range camera overrides `depth_max` to stop wasting the 12-bit
    resolution on distance it never sees (FR-CAM-039); an unset argument keeps the
    upstream default.

    Args:
        depth_min: Metres mapped to quantum 0, or None for the upstream default.
        depth_max: Metres mapped to the top quantum, or None for the default.
        shift: Pre-log offset in metres, or None for the default.
        use_log: Log vs linear quantisation, or None for the default.

    Returns:
        (DepthEncodingParams) Parameters carrying the upstream defaults plus overrides.
    """
    from lerobot.configs.video import (
        DEFAULT_DEPTH_MAX,
        DEFAULT_DEPTH_MIN,
        DEFAULT_DEPTH_SHIFT,
        DEFAULT_DEPTH_USE_LOG,
    )

    return DepthEncodingParams(
        depth_min=float(DEFAULT_DEPTH_MIN) if depth_min is None else depth_min,
        depth_max=float(DEFAULT_DEPTH_MAX) if depth_max is None else depth_max,
        shift=float(DEFAULT_DEPTH_SHIFT) if shift is None else shift,
        use_log=bool(DEFAULT_DEPTH_USE_LOG) if use_log is None else use_log,
    )
