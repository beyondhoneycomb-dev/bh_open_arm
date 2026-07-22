"""WP-3B-03 acceptance ② — the depth encoding params round-trip (offline path).

Runs here: min/max/shift/log are applied on encode and inverted on decode, recovering
a valid depth to within the 12-bit log grid's resolution. The encoder math is the
frozen LeRobot v0.6.0 transform (`06` §2.4); these tests pin the *round-trip contract*
and that the parameters actually move the mapping, not the upstream formula.
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.sensing.depth.encoding import (
    DepthEncodingError,
    DepthEncodingParams,
    default_depth_encoding_params,
)

# A comfortable mid-band avoids the near-`depth_min` edge where the log grid's relative
# resolution is coarsest; the round-trip bound below holds across it.
_BAND_MIN_MM = 300
_BAND_MAX_MM = 5000
_MAX_ABS_ERROR_MM = 2
_MAX_REL_ERROR = 0.01


def _band_depth() -> np.ndarray:
    """A deterministic (H, W, 1) uint16 mm depth frame spanning the mid-band."""
    values = np.arange(_BAND_MIN_MM, _BAND_MAX_MM, 7, dtype=np.uint16)
    return values.reshape(-1, 1, 1)


def test_round_trip_recovers_valid_depth_within_grid_resolution() -> None:
    """decode(encode(d)) recovers d to within the log grid's resolution (②)."""
    params = default_depth_encoding_params()
    depth = _band_depth()

    codes = params.encode(depth)
    recovered = params.decode(codes)

    assert codes.shape == depth.shape[:2]
    assert recovered.shape == depth.shape
    assert recovered.dtype == np.uint16

    abs_error = np.abs(recovered.astype(np.int64) - depth.astype(np.int64))
    rel_error = abs_error.ravel() / depth.ravel().astype(float)
    assert int(abs_error.max()) <= _MAX_ABS_ERROR_MM
    assert float(rel_error.max()) <= _MAX_REL_ERROR


def test_round_trip_is_idempotent_on_the_quantisation_grid() -> None:
    """Re-encoding a decoded frame yields identical codes — the grid is stable."""
    params = default_depth_encoding_params()
    depth = _band_depth()

    codes = params.encode(depth)
    codes_again = params.encode(params.decode(codes))
    assert np.array_equal(codes, codes_again)


def test_linear_quantisation_also_round_trips() -> None:
    """use_log=False takes the linear branch and still round-trips within tolerance."""
    params = default_depth_encoding_params(use_log=False)
    depth = _band_depth()

    recovered = params.decode(params.encode(depth))
    abs_error = np.abs(recovered.astype(np.int64) - depth.astype(np.int64))
    assert int(abs_error.max()) <= _MAX_ABS_ERROR_MM


def test_depth_max_changes_the_code_for_a_fixed_depth() -> None:
    """depth_max is applied: shrinking the range remaps a fixed depth to a new code."""
    depth = np.full((2, 2, 1), 2000, dtype=np.uint16)
    wide = default_depth_encoding_params(depth_max=10.0)
    narrow = default_depth_encoding_params(depth_max=3.0)
    assert not np.array_equal(wide.encode(depth), narrow.encode(depth))


def test_log_and_linear_differ_and_shift_is_applied() -> None:
    """use_log and shift are applied: each changes the code of a fixed depth."""
    depth = np.full((2, 2, 1), 1500, dtype=np.uint16)
    log_params = default_depth_encoding_params(use_log=True)
    linear_params = default_depth_encoding_params(use_log=False)
    shifted = default_depth_encoding_params(use_log=True, shift=1.0)

    assert not np.array_equal(log_params.encode(depth), linear_params.encode(depth))
    assert not np.array_equal(log_params.encode(depth), shifted.encode(depth))


def test_no_measurement_sentinel_does_not_survive_the_lossy_grid() -> None:
    """A 0 pixel decodes to depth_min, not 0 — motivating the separate fill-rate mask."""
    params = default_depth_encoding_params()
    holes = np.zeros((3, 3, 1), dtype=np.uint16)
    recovered = params.decode(params.encode(holes))
    assert int(recovered.min()) > 0
    assert int(round(params.depth_min * 1000)) == int(recovered.max())


def test_defaults_are_the_upstream_lerobot_constants() -> None:
    """The common defaults are read from LeRobot, not restated (single source of truth)."""
    from lerobot.configs.video import (
        DEFAULT_DEPTH_MAX,
        DEFAULT_DEPTH_MIN,
        DEFAULT_DEPTH_SHIFT,
        DEFAULT_DEPTH_USE_LOG,
    )

    params = default_depth_encoding_params()
    assert params.depth_min == DEFAULT_DEPTH_MIN
    assert params.depth_max == DEFAULT_DEPTH_MAX
    assert params.shift == DEFAULT_DEPTH_SHIFT
    assert params.use_log == DEFAULT_DEPTH_USE_LOG


def test_invalid_parameters_are_rejected() -> None:
    """A non-increasing range, or a log shift that is non-positive at depth_min, is refused."""
    with pytest.raises(DepthEncodingError, match="depth_min"):
        DepthEncodingParams(depth_min=5.0, depth_max=1.0, shift=3.5, use_log=True)
    with pytest.raises(DepthEncodingError, match="depth_min"):
        DepthEncodingParams(depth_min=1.0, depth_max=2.0, shift=-1.0, use_log=True)
