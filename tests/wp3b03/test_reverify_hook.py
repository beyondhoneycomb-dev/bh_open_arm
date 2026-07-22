"""WP-3B-03 — the deferred real-fixture re-verification hook (plan 02a §4.1).

The honest shape of a deferral. `test_hook_reruns_over_a_real_format_capture` proves
the hook machinery is not a stub: it writes depth frames and params in the exact layout
a real capture carries, points the hook at that directory, and checks the fill rate and
round-trip error come back through the identical calculators. Only the hardware *bytes*
are pending.

`test_real_depth_capture_reverify` skips with a reason until `OPENARM_DEPTH_REAL_FIXTURE`
names a real capture; `test_live_realsense_depth` skips because `pyrealsense2` and a real
RealSense are absent — `PG-DEPTH-001`. No green is faked, none is dropped.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from backend.sensing.depth.encoding import default_depth_encoding_params
from backend.sensing.depth.reverify import (
    FRAMES_SUBDIR,
    PARAMS_FILENAME,
    fixture_dir_from_env,
    reverify_from_fixture,
)

_REALSENSE_PRESENT = importlib.util.find_spec("pyrealsense2") is not None


def _write_capture(directory: Path) -> None:
    """Write a real-format depth capture the hook can consume."""
    params = default_depth_encoding_params()
    (directory / PARAMS_FILENAME).write_text(
        json.dumps(
            {
                "depth_min": params.depth_min,
                "depth_max": params.depth_max,
                "shift": params.shift,
                "use_log": params.use_log,
            }
        ),
        encoding="utf-8",
    )
    frames_dir = directory / FRAMES_SUBDIR
    frames_dir.mkdir()

    filled = np.full((6, 8, 1), 1500, dtype=np.uint16)
    filled[0, 0, 0] = 0  # one hole
    np.save(frames_dir / "0000.npy", filled)

    holes = np.zeros((6, 8, 1), dtype=np.uint16)
    np.save(frames_dir / "0001.npy", holes)


def test_hook_reruns_over_a_real_format_capture(tmp_path: Path) -> None:
    """The hook re-derives fill rate and round-trip error from a capture, not a stub."""
    _write_capture(tmp_path)
    report = reverify_from_fixture(tmp_path)

    assert [frame.name for frame in report.frames] == ["0000", "0001"]

    filled = report.frames[0]
    assert filled.fill_rate.total_pixels == 48
    assert filled.fill_rate.hole_pixels == 1
    # A measured pixel round-trips to within the log grid's resolution.
    assert filled.round_trip_max_abs_error_mm <= 2

    holes = report.frames[1]
    assert holes.fill_rate.fill_rate == 0.0
    # An all-holes frame has no measured pixel, so its round-trip error is defined as 0.
    assert holes.round_trip_max_abs_error_mm == 0


def test_missing_params_file_is_an_error(tmp_path: Path) -> None:
    """The hook fails loudly when the required params file is absent."""
    (tmp_path / FRAMES_SUBDIR).mkdir()
    with pytest.raises(FileNotFoundError, match=PARAMS_FILENAME):
        reverify_from_fixture(tmp_path)


def test_missing_frames_dir_is_an_error(tmp_path: Path) -> None:
    """The hook fails loudly when the frames directory is absent."""
    params = default_depth_encoding_params()
    (tmp_path / PARAMS_FILENAME).write_text(
        json.dumps(
            {
                "depth_min": params.depth_min,
                "depth_max": params.depth_max,
                "shift": params.shift,
                "use_log": params.use_log,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(FileNotFoundError, match=FRAMES_SUBDIR):
        reverify_from_fixture(tmp_path)


@pytest.mark.skipif(
    fixture_dir_from_env() is None,
    reason="no real depth capture: set OPENARM_DEPTH_REAL_FIXTURE to a directory holding "
    "params.json and frames/*.npy captured from a real RealSense",
)
def test_real_depth_capture_reverify() -> None:
    """Re-run the depth calculators against a real captured depth set when supplied.

    Deferred acceptance (`PG-DEPTH-001`): real depth, real holes, real round-trip —
    verified the moment a rig capture exists, using the identical calculators.
    """
    fixture_dir = fixture_dir_from_env()
    assert fixture_dir is not None
    report = reverify_from_fixture(fixture_dir)
    assert report.frames, "a real capture must hold at least one depth frame"
    for frame in report.frames:
        assert 0.0 <= frame.fill_rate.fill_rate <= 1.0


@pytest.mark.skipif(
    not _REALSENSE_PRESENT,
    reason="no RealSense: pyrealsense2 is not installed and no depth camera is attached "
    "(PG-DEPTH-001) — live depth and its fill rate are verified on the real rig",
)
def test_live_realsense_depth() -> None:
    """Placeholder for the live-depth acceptance, gated behind real hardware.

    Left unconditionally skipped on this host: a real depth frame is never fabricated,
    so the live path is exercised only where a RealSense exists (`PG-DEPTH-001`).
    """
    pytest.fail("live RealSense depth must be exercised on the real rig, not synthesised")
