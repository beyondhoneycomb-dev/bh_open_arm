"""Real-fixture re-verification hook (plan 02a §4.1) for the depth path (WP-3B-03).

The offline half of this WP runs here: the toggle/shape validation, the fill-rate
computation and the quantise/dequantise round-trip are pure functions over `(H, W, 1)`
uint16 arrays, so a synthetic frame and a real capture run through identical code
whatever produced them. What cannot run here is those same computations over *real*
sensor depth — real holes, a real near/far distribution — because no depth camera on
this host can be opened (`PG-DEPTH-001`); `real_depth_supported` reports why.

This hook is what the deferral ships. When a directory of real captured depth frames is
supplied via `OPENARM_DEPTH_REAL_FIXTURE`, `reverify_from_fixture` re-runs the identical
fill-rate and round-trip calculators against the real bytes; until then the bound test
skips with a reason. The round-trip error is measured over measured pixels only, since
the 0 = no-measurement sentinel is not expected to survive the lossy grid.

The fixture directory holds:

- `params.json`   — `{device, depth_min, depth_max, shift, use_log}` the capture used,
- `frames/*.npy`  — real `(H, W, 1)` uint16 depth frames (mm, 0 = no measurement).

`device` is required: a capture that does not name the family it came from is refused
rather than attributed to whichever family the reader assumed, since the conversion into
the transport is per-family and a capture that never went through one family's
conversion cannot be read as though it had. Frames are checked against the `CTR-PRIM@v1`
depth transport rather than coerced into it, because coercion is silent and wrong in the
exact case a stereo camera produces: a stereo SDK's depth measure is float metres
carrying NaN for unmatched pixels and ±inf for out-of-range ones, and casting that
straight to uint16 turns 1.5 m into 1 mm while the fill rate still reads ~100%.

Layout and dtype are necessary and not sufficient. `assert_capture_is_plausible` judges
the numbers themselves, because the two failures that survive every structural check —
a camera that returned nothing, and frames stored in a unit the capture did not declare
— both produce a perfectly well-formed file.
"""

from __future__ import annotations

import importlib.util
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import numpy as np
from numpy.typing import NDArray

from backend.sensing.depth.constants import (
    DEPTH_FRAME_CHANNELS,
    DEPTH_FRAME_DTYPE,
    DEPTH_NO_MEASUREMENT_MM,
    DEPTH_SDK_MODULE,
    DEPTH_USB_ID,
    DepthDevice,
)
from backend.sensing.depth.encoding import DepthEncodingParams
from backend.sensing.depth.fill_rate import FillRateReport, compute_fill_rate
from backend.sensing.depth.usb_link import (
    USB_SYSFS_ROOT,
    USB_VIDEO_INTERFACE_CLASS,
    probe_usb_link,
)
from backend.sensing.depth.version_gate import lerobot_backend_exists

FIXTURE_ENV_VAR = "OPENARM_DEPTH_REAL_FIXTURE"
PARAMS_FILENAME = "params.json"
FRAMES_SUBDIR = "frames"
FRAME_SUFFIX = ".npy"

# The `params.json` key naming the camera family that produced the capture.
PARAMS_DEVICE_FIELD = "device"

# Frames are `(H, W, C)` with the channel axis last, matching `depth_feature_shape`.
_FRAME_NDIM = 3

# `DepthEncodingParams` declares its range in metres; frames are `CTR-PRIM@v1`
# millimetres. The two meet only in the plausibility band, so the conversion lives here.
_MM_PER_METRE = 1000

# Below this fraction of measured pixels a frame carries no scene: a capped lens, a
# stream that never started, a range set past everything in front of the camera. The bar
# sits far under what a working stereo camera returns indoors so that a genuinely hard
# scene — glass, sky, an untextured wall — is not called broken, and far over the 0.0 a
# camera that returned nothing produces.
MIN_REAL_CAPTURE_FILL_RATE = 0.05


class DepthFixtureError(ValueError):
    """Raised when a real capture is not one this hook can read or believe.

    Both halves of that: a layout or dtype the hook does not read, and numbers that
    cannot have come from the camera and parameters the capture declares.
    """


@dataclass(frozen=True)
class DepthFrameReverify:
    """The re-derived measures of one real depth frame.

    Attributes:
        name: The frame file stem.
        fill_rate: The measured/hole split (FR-CAM-040).
        round_trip_max_abs_error_mm: Largest encode→decode error over measured
            pixels, in millimetres; 0 when the frame has no measured pixel.
        measured_depth_min_mm: Nearest measured depth in the frame, in millimetres.
        measured_depth_max_mm: Farthest measured depth in the frame, in millimetres.
            Both are 0 when the frame has no measured pixel, which is the transport's own
            no-measurement value rather than a separate absent marker.
    """

    name: str
    fill_rate: FillRateReport
    round_trip_max_abs_error_mm: int
    measured_depth_min_mm: int
    measured_depth_max_mm: int


@dataclass(frozen=True)
class DepthReverifyReport:
    """The result of re-running the depth calculators over one real capture.

    Attributes:
        device: The camera family the capture declared.
        params: The depth parameters the capture declared.
        frames: Per-frame re-derived measures, in file-name order.
    """

    device: DepthDevice
    params: DepthEncodingParams
    frames: tuple[DepthFrameReverify, ...]


def _usb_link_blockers(device: DepthDevice, sysfs_root: Path) -> list[str]:
    """The attachment blockers for a family whose USB identity is recorded.

    Empty for a family with no recorded identity: silence about a camera nobody can
    recognise is honest, a green about it would not be.
    """
    usb_id = DEPTH_USB_ID[device]
    if usb_id is None:
        return []
    vendor, product = usb_id
    link = probe_usb_link(usb_id, sysfs_root)
    if not link.present:
        return [f"no {vendor}:{product} camera is enumerated on USB"]
    if link.carries_video:
        return []
    return [
        f"the {vendor}:{product} camera is on a {link.link_speed_mbps} Mbit/s link "
        f"publishing interface class {'/'.join(link.interface_classes)} and no video class "
        f"{USB_VIDEO_INTERFACE_CLASS}, so it carries no stream to open — move it to a "
        "USB 3.0 port"
    ]


def real_depth_supported(
    device: DepthDevice, sysfs_root: Path = USB_SYSFS_ROOT
) -> tuple[bool, str]:
    """Report whether live depth can run here for this family, and why not when it cannot.

    Every blocker is reported rather than the first, because clearing one clears none of
    the others and they are not all software: the vendor SDK must be importable, LeRobot
    must ship a camera class for the family, and the camera must be attached over a link
    that carries a video interface. The last one is the one an operator cannot deduce —
    installing the SDK and finding a camera class leaves a full-speed-cabled camera
    exactly as mute as it was.

    Args:
        device: The depth camera family to judge.
        sysfs_root: The USB tree the attachment check reads; the kernel's own by default.

    Returns:
        (tuple[bool, str]) `(supported, reason)`; reason is empty when supported.
    """
    blockers: list[str] = []
    sdk_module = DEPTH_SDK_MODULE[device]
    if importlib.util.find_spec(sdk_module) is None:
        blockers.append(f"{sdk_module} is not installed")
    if not lerobot_backend_exists(device):
        blockers.append(f"the installed LeRobot has no camera class for {device.value!r}")
    blockers.extend(_usb_link_blockers(device, sysfs_root))
    if blockers:
        return False, "; ".join(blockers)
    return True, ""


def fixture_dir_from_env() -> Path | None:
    """Return the real-fixture directory named by the environment, if set and present."""
    raw = os.environ.get(FIXTURE_ENV_VAR)
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_dir() else None


def load_params(path: Path) -> tuple[DepthDevice, DepthEncodingParams]:
    """Load the camera family and depth parameters a real capture recorded.

    Args:
        path: A `params.json` holding `device` and the four quantiser settings.

    Returns:
        (tuple[DepthDevice, DepthEncodingParams]) The family and the parameters used.

    Raises:
        DepthFixtureError: If `device` is absent or names an unknown family.
    """
    spec = json.loads(path.read_text(encoding="utf-8"))
    known = sorted(member.value for member in DepthDevice)
    if PARAMS_DEVICE_FIELD not in spec:
        raise DepthFixtureError(
            f"{path} has no {PARAMS_DEVICE_FIELD!r} field; a capture must name the camera "
            f"family that produced it (one of {known}) so its depth is read as the transport "
            "it was converted to rather than the one this host happens to expect"
        )
    raw_device = spec[PARAMS_DEVICE_FIELD]
    try:
        device = DepthDevice(raw_device)
    except ValueError as error:
        raise DepthFixtureError(
            f"{path} names an unknown depth device {raw_device!r}; known families are {known}"
        ) from error
    params = DepthEncodingParams(
        depth_min=float(spec["depth_min"]),
        depth_max=float(spec["depth_max"]),
        shift=float(spec["shift"]),
        use_log=bool(spec["use_log"]),
    )
    return device, params


def load_frame(path: Path) -> NDArray[np.uint16]:
    """Load one captured depth frame, refusing anything not already in the transport.

    The refusal is the point. `np.load(...).astype(np.uint16)` accepts every wrong thing
    silently: float metres collapse to 0–10 mm, values past 65535 wrap to plausible
    mid-range depths, negatives wrap to ~65 m — and all of those pass the fill-rate and
    round-trip checks looking healthy. Converting a vendor measure into `CTR-PRIM@v1`
    uint16 millimetres is the capture tool's job, and the evidence that it happened is
    that the stored file already carries the right dtype.

    Args:
        path: A `.npy` holding an `(H, W, 1)` uint16 depth frame in millimetres.

    Returns:
        (NDArray[np.uint16]) The frame as stored.

    Raises:
        DepthFixtureError: If the dtype or the shape is not the contract's.
    """
    frame = np.load(path)
    if frame.dtype != DEPTH_FRAME_DTYPE:
        raise DepthFixtureError(
            f"{path} has dtype {frame.dtype!r}, expected {DEPTH_FRAME_DTYPE!r}: depth frames "
            f"are {DEPTH_FRAME_DTYPE} millimetres per CTR-PRIM@v1. Convert the vendor measure "
            "at capture time — a stereo SDK reports float metres with NaN/±inf for unmatched "
            f"and out-of-range pixels, which must become {DEPTH_NO_MEASUREMENT_MM} mm here"
        )
    if frame.ndim != _FRAME_NDIM or frame.shape[-1] != DEPTH_FRAME_CHANNELS:
        raise DepthFixtureError(
            f"{path} has shape {frame.shape!r}, expected (H, W, {DEPTH_FRAME_CHANNELS})"
        )
    # `np.load` is typed as Any; the two checks above are what make the cast true.
    return cast("NDArray[np.uint16]", frame)


def _measured_depth_range_mm(frame: NDArray[np.uint16]) -> tuple[int, int]:
    """Nearest and farthest measured depth in one frame, ignoring the hole sentinel."""
    measured = frame[frame != DEPTH_NO_MEASUREMENT_MM]
    if measured.size == 0:
        return DEPTH_NO_MEASUREMENT_MM, DEPTH_NO_MEASUREMENT_MM
    return int(measured.min()), int(measured.max())


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
        DepthFixtureError: If the params or any frame is not in the layout read here.
    """
    params_path = fixture_dir / PARAMS_FILENAME
    if not params_path.is_file():
        raise FileNotFoundError(f"missing {PARAMS_FILENAME} in {fixture_dir}")
    device, params = load_params(params_path)

    frames_dir = fixture_dir / FRAMES_SUBDIR
    if not frames_dir.is_dir():
        raise FileNotFoundError(f"missing {FRAMES_SUBDIR}/ in {fixture_dir}")

    frames: list[DepthFrameReverify] = []
    for frame_path in sorted(frames_dir.glob(f"*{FRAME_SUFFIX}")):
        frame = load_frame(frame_path)
        nearest, farthest = _measured_depth_range_mm(frame)
        frames.append(
            DepthFrameReverify(
                name=frame_path.stem,
                fill_rate=compute_fill_rate(frame),
                round_trip_max_abs_error_mm=_round_trip_error_mm(params, frame),
                measured_depth_min_mm=nearest,
                measured_depth_max_mm=farthest,
            )
        )
    return DepthReverifyReport(device=device, params=params, frames=tuple(frames))


def assert_capture_is_plausible(report: DepthReverifyReport) -> None:
    """Refuse a capture whose numbers cannot have come from what the capture declares.

    The two failures that survive every structural check, because both produce a
    well-formed file of the right dtype and shape:

    * the camera returned nothing — a capped lens, a stream that never started — which
      reads as a fill rate at or near zero;
    * the frames hold a unit the capture did not declare, which puts every measured depth
      outside the range `params.json` itself names. Metres written as millimetres land at
      a few mm, orders below any `depth_min` a camera is configured with.

    One failure it cannot see: a capture tool that wrapped a depth past the uint16
    ceiling before writing stores a plausible mid-range millimetre value, and nothing in
    the stored frame separates it from a real measurement at that distance. That one is
    stopped at capture time or not at all.

    Args:
        report: A capture already read by `reverify_from_fixture`.

    Raises:
        DepthFixtureError: If the capture holds no frame, if a frame is almost entirely
            holes, or if a frame's measured depths fall outside its own declared range.
    """
    if not report.frames:
        raise DepthFixtureError("a capture holds no depth frame, so there is nothing to judge")
    nearest_allowed_mm = round(report.params.depth_min * _MM_PER_METRE)
    farthest_allowed_mm = round(report.params.depth_max * _MM_PER_METRE)
    for frame in report.frames:
        measured_fraction = frame.fill_rate.fill_rate
        if measured_fraction < MIN_REAL_CAPTURE_FILL_RATE:
            raise DepthFixtureError(
                f"frame {frame.name!r} has fill rate {measured_fraction:.4f}, under "
                f"{MIN_REAL_CAPTURE_FILL_RATE}: a camera returning no measurement over "
                "essentially the whole frame is not looking at the scene"
            )
        if (
            frame.measured_depth_min_mm < nearest_allowed_mm
            or frame.measured_depth_max_mm > farthest_allowed_mm
        ):
            raise DepthFixtureError(
                f"frame {frame.name!r} measures {frame.measured_depth_min_mm}–"
                f"{frame.measured_depth_max_mm} mm, outside the {nearest_allowed_mm}–"
                f"{farthest_allowed_mm} mm its own {PARAMS_FILENAME} declares: either the "
                "frames are not in millimetres, or the declared range does not cover the "
                "scene the quantiser will be asked to encode"
            )
