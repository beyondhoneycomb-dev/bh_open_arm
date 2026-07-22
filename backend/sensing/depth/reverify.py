"""Real-fixture re-verification hook (plan 02a §4.1) for the depth path (WP-3B-03).

The offline half of this WP runs here: the toggle/shape validation, the fill-rate
computation and the quantise/dequantise round-trip are pure functions over
`(H, W, 1)` uint16 arrays, so a synthetic frame and a real RealSense capture run
through identical code. What cannot run here is those same computations over *real*
sensor depth — real holes, a real near/far distribution — because there is no
RealSense on this host (`PG-DEPTH-001`).

This hook is what the deferral ships. When a directory of real captured depth frames
is supplied (via `OPENARM_DEPTH_REAL_FIXTURE`), `reverify_from_fixture` re-runs the
identical fill-rate and round-trip calculators against the real bytes; until then the
bound test skips with a reason. The round-trip error is measured over measured pixels
only, since the 0 = no-measurement sentinel is not expected to survive the lossy grid.
The fixture directory holds:

- `params.json`   — `{depth_min, depth_max, shift, use_log}` the capture used,
- `frames/*.npy`  — real `(H, W, 1)` uint16 depth frames (mm, 0 = no measurement).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from backend.sensing.depth.constants import DEPTH_NO_MEASUREMENT_MM
from backend.sensing.depth.encoding import DepthEncodingParams
from backend.sensing.depth.fill_rate import FillRateReport, compute_fill_rate

FIXTURE_ENV_VAR = "OPENARM_DEPTH_REAL_FIXTURE"
PARAMS_FILENAME = "params.json"
FRAMES_SUBDIR = "frames"
FRAME_SUFFIX = ".npy"


@dataclass(frozen=True)
class DepthFrameReverify:
    """The re-derived measures of one real depth frame.

    Attributes:
        name: The frame file stem.
        fill_rate: The measured/hole split (FR-CAM-040).
        round_trip_max_abs_error_mm: Largest encode→decode error over measured
            pixels, in millimetres; 0 when the frame has no measured pixel.
    """

    name: str
    fill_rate: FillRateReport
    round_trip_max_abs_error_mm: int


@dataclass(frozen=True)
class DepthReverifyReport:
    """The result of re-running the depth calculators over one real capture.

    Attributes:
        params: The depth parameters the capture declared.
        frames: Per-frame re-derived measures, in file-name order.
    """

    params: DepthEncodingParams
    frames: tuple[DepthFrameReverify, ...]


def fixture_dir_from_env() -> Path | None:
    """Return the real-fixture directory named by the environment, if set and present."""
    raw = os.environ.get(FIXTURE_ENV_VAR)
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_dir() else None


def load_params(path: Path) -> DepthEncodingParams:
    """Load the depth parameters a real capture recorded.

    Args:
        path: A `params.json` holding `depth_min`/`depth_max`/`shift`/`use_log`.

    Returns:
        (DepthEncodingParams) The parameters the capture used.
    """
    spec = json.loads(path.read_text(encoding="utf-8"))
    return DepthEncodingParams(
        depth_min=float(spec["depth_min"]),
        depth_max=float(spec["depth_max"]),
        shift=float(spec["shift"]),
        use_log=bool(spec["use_log"]),
    )


def _round_trip_error_mm(params: DepthEncodingParams, frame: NDArray[np.uint16]) -> int:
    """Largest encode→decode error over the measured pixels of one frame."""
    decoded = params.decode(params.encode(frame))
    measured = frame != DEPTH_NO_MEASUREMENT_MM
    if not bool(measured.any()):
        return 0
    error = np.abs(decoded.astype(np.int32) - frame.astype(np.int32))
    return int(error[measured].max())


def reverify_from_fixture(fixture_dir: Path) -> DepthReverifyReport:
    """Re-run the depth calculators against a directory of real captured frames.

    Every computation is the one the synthetic tests exercise, pointed at real bytes —
    the point of the hook is that no path is re-implemented for hardware.

    Args:
        fixture_dir: Directory of captured depth frames (see the module docstring).

    Returns:
        (DepthReverifyReport) Per-frame fill rate and round-trip error under the
        capture's own parameters.

    Raises:
        FileNotFoundError: If `params.json` or the frames directory is absent.
    """
    params_path = fixture_dir / PARAMS_FILENAME
    if not params_path.is_file():
        raise FileNotFoundError(f"missing {PARAMS_FILENAME} in {fixture_dir}")
    params = load_params(params_path)

    frames_dir = fixture_dir / FRAMES_SUBDIR
    if not frames_dir.is_dir():
        raise FileNotFoundError(f"missing {FRAMES_SUBDIR}/ in {fixture_dir}")

    frames: list[DepthFrameReverify] = []
    for frame_path in sorted(frames_dir.glob(f"*{FRAME_SUFFIX}")):
        frame = np.load(frame_path).astype(np.uint16, copy=False)
        frames.append(
            DepthFrameReverify(
                name=frame_path.stem,
                fill_rate=compute_fill_rate(frame),
                round_trip_max_abs_error_mm=_round_trip_error_mm(params, frame),
            )
        )
    return DepthReverifyReport(params=params, frames=tuple(frames))
