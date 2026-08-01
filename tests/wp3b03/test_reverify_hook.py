"""WP-3B-03 — the deferred real-fixture re-verification hook (plan 02a §4.1).

The honest shape of a deferral. `test_hook_reruns_over_a_real_format_capture` proves the
hook machinery is not a stub: it writes depth frames and params in the exact layout a
real capture carries, points the hook at that directory, and checks the fill rate and
round-trip error come back through the identical calculators. Only the hardware *bytes*
are pending.

The refusals around it exist because the fixture is the one place a wrong depth frame
can enter the platform without a camera being involved, and because a stereo camera's
native measure is not this transport. Each refusal is driven through
`reverify_from_fixture` and not only through the function that implements it, since the
hook is the entry a rig capture actually arrives on and a refusal the hook does not
reach protects nothing. `test_a_float_metres_capture_is_refused` and
`test_a_signed_millimetre_capture_is_refused` also pin what the refusals are worth, by
measuring what a bare cast would have produced from the same files.

`read_capture` appears where a capture's own numbers are the subject: it reads without
judging, so a frame that is structurally perfect and numerically impossible can be
measured before being refused. Everywhere else the entry is `reverify_from_fixture`,
which reads and judges.

The content refusals are the same ones the deferred rig acceptance leans on. That is
what makes the acceptance non-vacuous while the hardware is absent: broken captures are
fabricated here and shown to be refused, so the rig test asserts a predicate whose bite
is already established rather than a range every possible frame satisfies.

`test_real_depth_capture_reverify` skips until `OPENARM_DEPTH_REAL_FIXTURE` names a real
capture; `test_live_depth_per_family` skips with the reasons each family is unavailable —
for the ZED fitted to this rig, `pyzed` is absent, LeRobot ships no ZED camera class, and
the camera is cabled onto a link that carries no video interface (`PG-DEPTH-001`). No
green is faked, none is dropped.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray

from backend.sensing.depth.constants import (
    DEPTH_SDK_MODULE,
    DEPTH_USB_ID,
    STEREOLABS_USB_VENDOR_ID,
    ZED_MINI_USB_PRODUCT_ID,
    DepthDevice,
)
from backend.sensing.depth.encoding import default_depth_encoding_params
from backend.sensing.depth.fill_rate import compute_fill_rate
from backend.sensing.depth.reverify import (
    FRAMES_SUBDIR,
    MIN_REAL_CAPTURE_FILL_RATE,
    PARAMS_DEVICE_FIELD,
    PARAMS_FILENAME,
    DepthFixtureError,
    assert_capture_is_plausible,
    fixture_dir_from_env,
    load_frame,
    read_capture,
    real_depth_supported,
    reverify_from_fixture,
)
from backend.sensing.depth.usb_link import (
    USB_SYSFS_ROOT,
    USB_VIDEO_INTERFACE_CLASS,
    probe_usb_link,
)

_HEIGHT = 6
_WIDTH = 8
_MID_BAND_MM = 1500
_MAX_ABS_ERROR_MM = 2

# A second depth, near the top of the default `[0.01, 10.0] m` range, where the 12-bit
# log grid is coarser than it is at `_MID_BAND_MM`. A frame carrying both therefore has
# a known non-zero max round-trip error and two different range ends, neither of which a
# frame at one depth has — there, a constant and a measurement are the same number. Both
# figures are grid properties: they move if `06` §2.4's encoder does, and not otherwise.
_FAR_BAND_MM = 9900
_TWO_BAND_ROUND_TRIP_ERROR_MM = 2

# What the same frame's round-trip error would read as if the hole were counted: the
# encoder maps the 0 sentinel to `depth_min`, and 0.01 m is 10 mm away from 0.
_ROUND_TRIP_ERROR_MM_COUNTING_THE_HOLE = 10

# A depth beyond the uint16 millimetre ceiling and a depth in metres: the two values
# whose silent coercion `load_frame` exists to stop.
_BEYOND_UINT16_MM = 70000.0
_MID_BAND_METRES = 1.5

# Millimetres in a signed 16-bit frame, which is what a capture tool that treats "no
# return" as a negative writes. Same width as the transport, different meaning.
_SIGNED_NO_RETURN_MM = -1
_SIGNED_NO_RETURN_READ_AS_UNSIGNED_MM = 65535

# 1.5 m written as though it were millimetres. A capture tool that skipped the unit
# conversion but did cast to uint16 produces exactly this, and it is well-formed.
_MID_BAND_AS_BARE_METRES_MM = 1

# Past the 10 m the default quantiser range declares, so the frames the encoder is about
# to be handed carry depth the encoder cannot represent.
_BEYOND_DECLARED_RANGE_MM = 20000

# The ZED Mini's enumeration as measured on this rig: full speed, one HID interface, no
# video one. Written into a fabricated sysfs tree rather than read from the host, so the
# refusal is exercised identically on a bench with nothing plugged in.
_ZED_SYSFS_NAME = "3-10.3.1.3.2"
_FULL_SPEED_MBPS = 12
_SUPERSPEED_MBPS = 5000
_USB_HID_INTERFACE_CLASS = "03"

# A Stereolabs product that is not the ZED Mini, for the case where the vendor matches
# and the product does not.
_OTHER_STEREOLABS_PRODUCT_ID = "0001"

# The kernel's own USB device tree, spelled out here so the default the probe carries is
# held against a value written down twice rather than against itself.
_KERNEL_USB_DEVICES_PATH = "/sys/bus/usb/devices"
_SYSFS_MOUNT = Path("/sys")

# The descriptor strings the kernel reads out of the camera itself. They select the
# device for the identity check below, so that the recorded vendor/product pair is the
# thing being judged rather than the thing doing the selecting.
_ZED_USB_MANUFACTURER = "STEREOLABS"
_ZED_USB_PRODUCT_PREFIX = "ZED"


def _write_params(directory: Path, device: str | None) -> None:
    """Write a capture's params.json, omitting `device` entirely when it is None."""
    params = default_depth_encoding_params()
    spec: dict[str, object] = {
        "depth_min": params.depth_min,
        "depth_max": params.depth_max,
        "shift": params.shift,
        "use_log": params.use_log,
    }
    if device is not None:
        spec[PARAMS_DEVICE_FIELD] = device
    (directory / PARAMS_FILENAME).write_text(json.dumps(spec), encoding="utf-8")


def _write_frames(directory: Path, frames: dict[str, np.ndarray]) -> None:
    """Write a ZED capture carrying the default params and the given frames.

    Takes any dtype: the refusals under test are the ones that fire on a frame the
    transport does not accept, so the helper cannot be the thing that rejects it.
    """
    _write_params(directory, DepthDevice.STEREOLABS_ZED.value)
    frames_dir = directory / FRAMES_SUBDIR
    frames_dir.mkdir()
    for name, frame in frames.items():
        np.save(frames_dir / f"{name}.npy", frame)


def _filled_frame(depth_mm: int) -> NDArray[np.uint16]:
    """A frame at one depth with a single hole, the shape a working capture has."""
    frame = np.full((_HEIGHT, _WIDTH, 1), depth_mm, dtype=np.uint16)
    frame[0, 0, 0] = 0
    return frame


def _two_band_frame(near_mm: int, far_mm: int) -> NDArray[np.uint16]:
    """A frame with a near half, a far half and one hole.

    A scene, rather than a wall: with one depth everywhere, the nearest and farthest
    measured depth are the same number and neither can be told from the other.
    """
    frame = np.full((_HEIGHT, _WIDTH, 1), near_mm, dtype=np.uint16)
    frame[_HEIGHT // 2 :, :, 0] = far_mm
    frame[0, 0, 0] = 0
    return frame


def _write_capture(directory: Path) -> None:
    """Write a real-format depth capture the hook can consume."""
    _write_frames(
        directory,
        {
            "0000": _filled_frame(_MID_BAND_MM),
            "0001": np.zeros((_HEIGHT, _WIDTH, 1), dtype=np.uint16),
        },
    )


def _write_usb_device(
    sysfs_root: Path,
    name: str,
    usb_id: tuple[str, str],
    speed_mbps: int,
    interface_classes: tuple[str, ...],
) -> None:
    """Write one USB device into a sysfs tree in the layout the kernel publishes.

    The attribute names are spelled out rather than imported, because what is under test
    is that the probe reads the kernel's names and not names of its own.
    """
    device_dir = sysfs_root / name
    device_dir.mkdir(parents=True)
    (device_dir / "idVendor").write_text(f"{usb_id[0]}\n", encoding="utf-8")
    (device_dir / "idProduct").write_text(f"{usb_id[1]}\n", encoding="utf-8")
    (device_dir / "speed").write_text(f"{speed_mbps}\n", encoding="utf-8")
    for index, interface_class in enumerate(interface_classes):
        interface_dir = device_dir / f"{name}:1.{index}"
        interface_dir.mkdir()
        (interface_dir / "bInterfaceClass").write_text(f"{interface_class}\n", encoding="utf-8")


def _zed_sysfs(tmp_path: Path, speed_mbps: int, interface_classes: tuple[str, ...]) -> Path:
    """A sysfs tree holding one ZED Mini attached the given way."""
    sysfs_root = tmp_path / "usb-devices"
    sysfs_root.mkdir(parents=True)
    _write_usb_device(
        sysfs_root,
        _ZED_SYSFS_NAME,
        (STEREOLABS_USB_VENDOR_ID, ZED_MINI_USB_PRODUCT_ID),
        speed_mbps,
        interface_classes,
    )
    return sysfs_root


def test_hook_reruns_over_a_real_format_capture(tmp_path: Path) -> None:
    """The hook re-derives fill rate and round-trip error from a capture, not a stub.

    Read without judging, because the all-holes frame this exercises is exactly what
    `assert_capture_is_plausible` refuses; what is under test here is that the numbers
    come back at all.
    """
    _write_capture(tmp_path)
    report = read_capture(tmp_path)

    assert report.device is DepthDevice.STEREOLABS_ZED
    assert [frame.name for frame in report.frames] == ["0000", "0001"]

    filled = report.frames[0]
    assert filled.fill_rate.total_pixels == _HEIGHT * _WIDTH
    assert filled.fill_rate.hole_pixels == 1
    # A measured pixel round-trips to within the log grid's resolution.
    assert filled.round_trip_max_abs_error_mm <= _MAX_ABS_ERROR_MM
    # The hole is excluded from the depth range, or every frame would read as reaching 0.
    assert filled.measured_depth_min_mm == _MID_BAND_MM
    assert filled.measured_depth_max_mm == _MID_BAND_MM

    holes = report.frames[1]
    assert holes.fill_rate.fill_rate == 0.0
    # An all-holes frame has no measured pixel, so its round-trip error is defined as 0.
    assert holes.round_trip_max_abs_error_mm == 0
    assert (holes.measured_depth_min_mm, holes.measured_depth_max_mm) == (0, 0)


def test_the_round_trip_error_is_the_grids_own_and_excludes_the_hole(tmp_path: Path) -> None:
    """The round-trip error is the loss the encoder actually inflicted on this frame.

    A bound is not a measurement. `_MAX_ABS_ERROR_MM` is an upper limit, and every
    constant a broken calculator could return sits under it — including the 0 an
    all-holes frame legitimately reports. The exact value, taken over a scene the log
    grid resolves unevenly, is what a constant cannot satisfy; keeping it under the
    hole's own error is what shows the sentinel is excluded rather than merely small.
    """
    _write_frames(tmp_path, {"0000": _two_band_frame(_MID_BAND_MM, _FAR_BAND_MM)})
    frame = reverify_from_fixture(tmp_path).frames[0]

    assert frame.round_trip_max_abs_error_mm == _TWO_BAND_ROUND_TRIP_ERROR_MM
    assert frame.round_trip_max_abs_error_mm < _ROUND_TRIP_ERROR_MM_COUNTING_THE_HOLE


def test_the_depth_range_is_the_scenes_near_and_far_ends(tmp_path: Path) -> None:
    """Nearest and farthest are two different measurements of a scene with depth in it.

    A frame at a single depth reports the same number twice, so it cannot tell a nearest
    that reads the far end — or a farthest that reads the near one — from a correct
    answer. Both mistakes let a capture whose deepest pixel is past the declared range
    through the plausibility judgment, which compares exactly these two numbers.
    """
    _write_frames(tmp_path, {"0000": _two_band_frame(_MID_BAND_MM, _FAR_BAND_MM)})
    frame = reverify_from_fixture(tmp_path).frames[0]

    assert frame.measured_depth_min_mm == _MID_BAND_MM
    assert frame.measured_depth_max_mm == _FAR_BAND_MM


def test_missing_params_file_is_an_error(tmp_path: Path) -> None:
    """The hook fails loudly when the required params file is absent."""
    (tmp_path / FRAMES_SUBDIR).mkdir()
    with pytest.raises(FileNotFoundError, match=PARAMS_FILENAME):
        reverify_from_fixture(tmp_path)


def test_missing_frames_dir_is_an_error(tmp_path: Path) -> None:
    """The hook fails loudly when the frames directory is absent."""
    _write_params(tmp_path, DepthDevice.INTEL_REALSENSE.value)
    with pytest.raises(FileNotFoundError, match=FRAMES_SUBDIR):
        reverify_from_fixture(tmp_path)


def test_a_capture_without_a_device_field_is_refused(tmp_path: Path) -> None:
    """A capture that names no family is refused, not attributed to an assumed one.

    The four quantiser settings alone do not say which conversion the frames went
    through, and a reader that supplies the family reads a capture as though it came
    from a camera that never produced it.
    """
    _write_params(tmp_path, device=None)
    (tmp_path / FRAMES_SUBDIR).mkdir()
    with pytest.raises(DepthFixtureError, match=PARAMS_DEVICE_FIELD):
        reverify_from_fixture(tmp_path)


def test_a_capture_naming_an_unknown_device_is_refused(tmp_path: Path) -> None:
    """A family this platform has no backend decision for cannot be read."""
    _write_params(tmp_path, device="oak_d")
    (tmp_path / FRAMES_SUBDIR).mkdir()
    with pytest.raises(DepthFixtureError, match="unknown depth device"):
        reverify_from_fixture(tmp_path)


def test_a_float_metres_capture_is_refused(tmp_path: Path) -> None:
    """A stereo SDK's native float-metres measure is refused, not silently cast.

    The second half is what the refusal is worth: a bare cast of the same file reports a
    fully filled frame whose every depth is off by a factor of 1000, and no downstream
    check catches it because the numbers are individually plausible.
    """
    frame_path = tmp_path / "0000.npy"
    stereo_native = np.full((_HEIGHT, _WIDTH, 1), _MID_BAND_METRES, dtype=np.float32)
    stereo_native[0, 0, 0] = np.nan  # unmatched pixel
    np.save(frame_path, stereo_native)

    with pytest.raises(DepthFixtureError, match="dtype"):
        load_frame(frame_path)

    # NaN raises a cast warning on the way to 0; the whole point here is to observe the
    # coercion's output rather than to be stopped by it.
    with np.errstate(invalid="ignore"):
        coerced = np.load(frame_path).astype(np.uint16)
    assert compute_fill_rate(coerced).fill_rate == pytest.approx(1.0 - 1 / (_HEIGHT * _WIDTH))
    assert int(coerced[1, 1, 0]) == 1  # 1.5 m read as 1 mm


def test_the_hook_itself_refuses_a_float_metres_frame(tmp_path: Path) -> None:
    """The dtype refusal holds on `reverify_from_fixture`, not only on `load_frame`.

    This is the entry a rig capture arrives on. A hook that read its frames with a bare
    `np.load` would leave `load_frame`'s refusal true and unreached, and report a fill
    rate near 1.0 and a round-trip error of a few millimetres for a capture in metres —
    numbers that read as an excellent result.
    """
    stereo_native = np.full((_HEIGHT, _WIDTH, 1), _MID_BAND_METRES, dtype=np.float32)
    stereo_native[0, 0, 0] = np.nan  # unmatched pixel
    _write_frames(tmp_path, {"0000": stereo_native})

    with pytest.raises(DepthFixtureError, match="dtype"):
        reverify_from_fixture(tmp_path)


def test_a_signed_millimetre_capture_is_refused(tmp_path: Path) -> None:
    """A same-width signed frame is refused: the dtype is the transport, not its width.

    `int16` is the trap a width comparison walks into, and it is what a capture tool
    writing signed millimetres produces — negative where the camera reported no return.
    The file is two bytes a pixel and `(H, W, 1)`, so only the dtype separates it from
    the transport; read as the unsigned transport it declares itself to be, those
    no-return pixels are depths near 65 m, which the fill rate counts as measurements.
    """
    frame_path = tmp_path / "0000.npy"
    signed = np.full((_HEIGHT, _WIDTH, 1), _MID_BAND_MM, dtype=np.int16)
    signed[0, 0, 0] = _SIGNED_NO_RETURN_MM
    np.save(frame_path, signed)

    with pytest.raises(DepthFixtureError, match="dtype"):
        load_frame(frame_path)

    coerced = np.load(frame_path).astype(np.uint16)
    assert int(coerced[0, 0, 0]) == _SIGNED_NO_RETURN_READ_AS_UNSIGNED_MM
    assert compute_fill_rate(coerced).fill_rate == 1.0  # the hole became the farthest pixel


def test_the_hook_itself_refuses_a_signed_millimetre_frame(tmp_path: Path) -> None:
    """The signed-dtype refusal holds on the entry a rig capture arrives on."""
    signed = np.full((_HEIGHT, _WIDTH, 1), _MID_BAND_MM, dtype=np.int16)
    signed[0, 0, 0] = _SIGNED_NO_RETURN_MM
    _write_frames(tmp_path, {"0000": signed})

    with pytest.raises(DepthFixtureError, match="dtype"):
        reverify_from_fixture(tmp_path)


def test_the_hook_itself_refuses_a_frame_of_the_wrong_shape(tmp_path: Path) -> None:
    """The shape refusal holds on `reverify_from_fixture` too, on the same reasoning."""
    _write_frames(tmp_path, {"0000": np.zeros((_HEIGHT, _WIDTH), dtype=np.uint16)})

    with pytest.raises(DepthFixtureError, match="shape"):
        reverify_from_fixture(tmp_path)


def test_an_out_of_range_capture_is_refused_before_it_wraps(tmp_path: Path) -> None:
    """A depth past the uint16 ceiling is refused, not wrapped into the mid band."""
    frame_path = tmp_path / "0000.npy"
    np.save(frame_path, np.full((_HEIGHT, _WIDTH, 1), _BEYOND_UINT16_MM, dtype=np.float32))

    with pytest.raises(DepthFixtureError, match="dtype"):
        load_frame(frame_path)

    # 70 m wraps to a plausible 4.46 m rather than to a hole or a saturated value.
    wrapped = int(np.load(frame_path).astype(np.uint16)[0, 0, 0])
    assert 0 < wrapped < _BEYOND_UINT16_MM


@pytest.mark.parametrize(
    "shape",
    [(_HEIGHT, _WIDTH), (_HEIGHT, _WIDTH, 3), (_HEIGHT * _WIDTH,)],
)
def test_a_frame_of_the_wrong_shape_is_refused(tmp_path: Path, shape: tuple[int, ...]) -> None:
    """A frame missing the channel axis, or carrying an RGB one, is refused."""
    frame_path = tmp_path / "0000.npy"
    np.save(frame_path, np.zeros(shape, dtype=np.uint16))
    with pytest.raises(DepthFixtureError, match="shape"):
        load_frame(frame_path)


def test_a_converted_stereo_frame_reads_the_same_as_a_projector_one(tmp_path: Path) -> None:
    """Fill rate is defined on the transport, so the sensing method does not change it.

    Once a stereo frame's unmatched and out-of-range pixels have become the 0 sentinel,
    it is indistinguishable from a projector camera's frame with the same holes — which
    is why every calculator in this package is device-agnostic and only the conversion
    into the transport is not.
    """
    projector = np.full((_HEIGHT, _WIDTH, 1), _MID_BAND_MM, dtype=np.uint16)
    projector[0, 0, 0] = 0  # pattern not returned

    stereo = np.full((_HEIGHT, _WIDTH, 1), _MID_BAND_MM, dtype=np.uint16)
    stereo[0, 0, 0] = 0  # pair did not match

    assert compute_fill_rate(projector) == compute_fill_rate(stereo)


def test_a_working_capture_is_plausible(tmp_path: Path) -> None:
    """The plausibility judgment accepts a capture with a scene in it."""
    _write_frames(tmp_path, {"0000": _filled_frame(_MID_BAND_MM)})
    assert_capture_is_plausible(read_capture(tmp_path))


def test_a_capture_that_measured_nothing_is_refused(tmp_path: Path) -> None:
    """A camera that returned no measurement anywhere is refused, not scored.

    The failure a fill rate bounded to `[0, 1]` cannot express: a capped lens, a stream
    that never started and a range set past the whole scene all arrive as 0.0, which is
    inside every such bound.
    """
    _write_frames(tmp_path, {"0000": np.zeros((_HEIGHT, _WIDTH, 1), dtype=np.uint16)})
    with pytest.raises(DepthFixtureError, match="fill rate"):
        assert_capture_is_plausible(read_capture(tmp_path))


def test_the_hook_itself_refuses_an_implausible_capture(tmp_path: Path) -> None:
    """The hook judges what it reads; no report comes back out of it unjudged.

    The hook is where a rig capture arrives, and a judgment a caller has to know to ask
    for is a judgment that capture can arrive without. A blind capture is the case that
    shows the difference: structurally flawless, and the camera saw nothing.
    """
    _write_frames(tmp_path, {"0000": np.zeros((_HEIGHT, _WIDTH, 1), dtype=np.uint16)})
    with pytest.raises(DepthFixtureError, match="fill rate"):
        reverify_from_fixture(tmp_path)


@pytest.mark.parametrize(
    ("broken", "expected"),
    [
        (np.zeros((_HEIGHT, _WIDTH, 1), dtype=np.uint16), "fill rate"),
        (_filled_frame(_BEYOND_DECLARED_RANGE_MM), "outside"),
    ],
)
def test_every_frame_is_judged_not_only_the_first(
    tmp_path: Path, broken: NDArray[np.uint16], expected: str
) -> None:
    """A later frame that is broken is refused, and named, on a healthy first frame.

    A capture is a sequence, and the failures the judgment exists for arrive part-way
    through one: a lens capped between takes, the arm carrying the camera past the far
    end of the declared range. Judging only what came first accepts every one of those
    and reports the capture as sound.
    """
    _write_frames(tmp_path, {"0000": _filled_frame(_MID_BAND_MM), "0001": broken})
    with pytest.raises(DepthFixtureError, match=expected) as refusal:
        assert_capture_is_plausible(read_capture(tmp_path))
    assert "'0001'" in str(refusal.value)


def test_a_capture_left_in_metres_is_refused_by_its_own_declared_range(tmp_path: Path) -> None:
    """Frames holding metres cast to uint16 are refused on the depths themselves.

    Well-formed in every structural sense — uint16, `(H, W, 1)`, fill rate 1.0 — and
    every depth is a thousandth of what it should be, which lands orders below the
    `depth_min` the capture's own params declare.
    """
    metres_as_mm = np.full((_HEIGHT, _WIDTH, 1), _MID_BAND_AS_BARE_METRES_MM, dtype=np.uint16)
    _write_frames(tmp_path, {"0000": metres_as_mm})

    report = read_capture(tmp_path)
    assert report.frames[0].fill_rate.fill_rate == 1.0  # nothing structural to catch
    with pytest.raises(DepthFixtureError, match="outside"):
        assert_capture_is_plausible(report)


def test_a_capture_past_its_declared_range_is_refused(tmp_path: Path) -> None:
    """Depth the declared quantiser cannot represent is refused before it is encoded.

    The encoder clamps at `depth_max`, so a scene deeper than the range the capture
    declares is destroyed silently at encode time rather than reported.
    """
    _write_frames(tmp_path, {"0000": _filled_frame(_BEYOND_DECLARED_RANGE_MM)})
    with pytest.raises(DepthFixtureError, match="outside"):
        assert_capture_is_plausible(read_capture(tmp_path))


def test_a_capture_with_no_frames_is_refused(tmp_path: Path) -> None:
    """An empty frames directory is a capture that measured nothing at all."""
    _write_frames(tmp_path, {})
    with pytest.raises(DepthFixtureError, match="no depth frame"):
        assert_capture_is_plausible(read_capture(tmp_path))


def test_the_fill_rate_bar_sits_between_a_blind_camera_and_a_hard_scene() -> None:
    """The bar refuses a camera that returned nothing without judging a sparse scene.

    A threshold nobody can reach and a threshold nothing can fail are the same defect;
    this pins which side of it the two cases sit on.
    """
    assert 0.0 < MIN_REAL_CAPTURE_FILL_RATE < 0.2


@pytest.mark.skipif(
    fixture_dir_from_env() is None,
    reason="no real depth capture: set OPENARM_DEPTH_REAL_FIXTURE to a directory holding "
    "params.json (with a 'device' field) and frames/*.npy of (H, W, 1) uint16 millimetre "
    "depth captured from the depth camera fitted to the rig",
)
def test_real_depth_capture_reverify() -> None:
    """Re-run the depth calculators against a real captured depth set when supplied.

    Deferred acceptance (`PG-DEPTH-001`): real depth, real holes, real round-trip, judged
    by `assert_capture_is_plausible`. That judgment is the same one the fabricated blind,
    metres and out-of-range captures above are shown to fail, so what this asserts has a
    demonstrated failure mode before any hardware arrives — the bytes are pending, the
    predicate is not.
    """
    fixture_dir = fixture_dir_from_env()
    assert fixture_dir is not None
    reverify_from_fixture(fixture_dir)


@pytest.mark.parametrize("device", list(DepthDevice))
def test_live_depth_per_family(device: DepthDevice) -> None:
    """Live depth acceptance, skipped per family with the reason it cannot run here.

    A real depth frame is never fabricated, so this fails rather than passes if it is
    ever reached without the family's SDK and LeRobot backend both present.
    """
    supported, reason = real_depth_supported(device)
    if not supported:
        pytest.skip(f"no live depth for {device.value} (PG-DEPTH-001): {reason}")
    pytest.fail(f"live {device.value} depth must be exercised on the real rig, not synthesised")


def test_the_zed_is_unavailable_for_three_separate_reasons(tmp_path: Path) -> None:
    """The ZED deferral names the SDK, the missing backend and the cabling.

    Each is independent, so any reason that named a subset would promise a fix that does
    not arrive. The cabling is the one an operator cannot deduce from software: with
    `pyzed` installed and a LeRobot ZED class in hand, a camera on a full-speed link is
    exactly as mute as before, and the remedy is a different port rather than a download.
    """
    sysfs_root = _zed_sysfs(tmp_path, _FULL_SPEED_MBPS, (_USB_HID_INTERFACE_CLASS,))
    supported, reason = real_depth_supported(DepthDevice.STEREOLABS_ZED, sysfs_root)

    assert not supported
    assert DEPTH_SDK_MODULE[DepthDevice.STEREOLABS_ZED] in reason
    assert "no camera class" in reason
    assert f"{_FULL_SPEED_MBPS} Mbit/s" in reason
    assert "USB 3.0" in reason


def test_a_superspeed_zed_clears_the_cabling_blocker_and_only_that_one(tmp_path: Path) -> None:
    """Re-cabling removes the link blocker and leaves the two software ones standing.

    Without this the link blocker could be a sentence the deferral always prints, which
    would make it a decoration rather than a judgment.
    """
    sysfs_root = _zed_sysfs(
        tmp_path, _SUPERSPEED_MBPS, (USB_VIDEO_INTERFACE_CLASS, _USB_HID_INTERFACE_CLASS)
    )
    supported, reason = real_depth_supported(DepthDevice.STEREOLABS_ZED, sysfs_root)

    assert not supported
    assert DEPTH_SDK_MODULE[DepthDevice.STEREOLABS_ZED] in reason
    assert "no camera class" in reason
    assert "Mbit/s" not in reason
    assert "enumerated on USB" not in reason


def _fitted_stereolabs_device_dir() -> Path | None:
    """The sysfs entry the kernel labelled as a Stereolabs ZED, located by its strings."""
    try:
        entries = sorted(USB_SYSFS_ROOT.iterdir())
    except OSError:
        return None
    for entry in entries:
        try:
            manufacturer = (entry / "manufacturer").read_text(encoding="utf-8").strip()
            product = (entry / "product").read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if manufacturer.upper() == _ZED_USB_MANUFACTURER and product.upper().startswith(
            _ZED_USB_PRODUCT_PREFIX
        ):
            return entry
    return None


@pytest.mark.skipif(
    _fitted_stereolabs_device_dir() is None,
    reason="no Stereolabs camera is enumerated on this host, so the recorded USB identity "
    "has no hardware to be checked against",
)
def test_the_recorded_usb_identity_is_the_fitted_cameras() -> None:
    """The recorded vendor/product pair is the one the fitted camera enumerates with.

    That pair is the probe's only matching key, so one wrong digit turns every attachment
    report into "nothing is plugged in" for a camera sitting on the bus — and the
    deferral would then name a blocker that is not the real one.

    Only the hardware can say the digits are right; a check written against the constants
    themselves passes on any value. So this runs where the camera is and skips where it
    is not, and the device is found by the descriptor strings the camera reports rather
    than by the ids under test.
    """
    device_dir = _fitted_stereolabs_device_dir()
    assert device_dir is not None
    vendor = (device_dir / "idVendor").read_text(encoding="utf-8").strip()
    product = (device_dir / "idProduct").read_text(encoding="utf-8").strip()
    assert (vendor, product) == (STEREOLABS_USB_VENDOR_ID, ZED_MINI_USB_PRODUCT_ID)


def test_a_camera_nobody_plugged_in_is_reported_as_absent(tmp_path: Path) -> None:
    """An empty USB tree reports the camera missing rather than mis-cabled."""
    sysfs_root = tmp_path / "usb-devices"
    sysfs_root.mkdir()
    _, reason = real_depth_supported(DepthDevice.STEREOLABS_ZED, sysfs_root)
    assert f"no {STEREOLABS_USB_VENDOR_ID}:{ZED_MINI_USB_PRODUCT_ID} camera" in reason


def test_a_family_with_no_recorded_usb_identity_makes_no_claim_about_cabling(
    tmp_path: Path,
) -> None:
    """A family nobody can recognise on USB is reported without a link verdict.

    No RealSense is fitted and Intel's product id differs per model, so there is nothing
    to match on; inventing one would put a guess where the deferral reads as measurement.
    """
    assert DEPTH_USB_ID[DepthDevice.INTEL_REALSENSE] is None
    sysfs_root = tmp_path / "usb-devices"
    sysfs_root.mkdir()
    _, reason = real_depth_supported(DepthDevice.INTEL_REALSENSE, sysfs_root)
    assert "USB" not in reason


def test_every_named_family_has_a_usb_decision() -> None:
    """No family can be judged on cabling without a recorded decision about its identity."""
    assert set(DEPTH_USB_ID) == set(DepthDevice)


def test_the_probe_reads_the_link_speed_and_every_interface_class(tmp_path: Path) -> None:
    """The probe reports what the kernel enumerated, not merely that something matched.

    `carries_video` is the decisive half: a device can be present, correctly named and
    the right vendor/product pair while publishing no interface a stream can travel on.
    """
    usb_id = (STEREOLABS_USB_VENDOR_ID, ZED_MINI_USB_PRODUCT_ID)

    as_fitted = probe_usb_link(
        usb_id, _zed_sysfs(tmp_path / "fitted", _FULL_SPEED_MBPS, (_USB_HID_INTERFACE_CLASS,))
    )
    assert as_fitted.present
    assert as_fitted.link_speed_mbps == _FULL_SPEED_MBPS
    assert as_fitted.interface_classes == (_USB_HID_INTERFACE_CLASS,)
    assert not as_fitted.carries_video

    recabled = probe_usb_link(
        usb_id,
        _zed_sysfs(
            tmp_path / "recabled",
            _SUPERSPEED_MBPS,
            (USB_VIDEO_INTERFACE_CLASS, _USB_HID_INTERFACE_CLASS),
        ),
    )
    assert recabled.link_speed_mbps == _SUPERSPEED_MBPS
    assert recabled.carries_video


def test_the_probe_does_not_match_a_different_camera(tmp_path: Path) -> None:
    """A device sharing the vendor but not the product is not the fitted camera."""
    sysfs_root = tmp_path / "usb-devices"
    sysfs_root.mkdir()
    _write_usb_device(
        sysfs_root,
        "3-1",
        (STEREOLABS_USB_VENDOR_ID, _OTHER_STEREOLABS_PRODUCT_ID),
        _SUPERSPEED_MBPS,
        (USB_VIDEO_INTERFACE_CLASS,),
    )
    link = probe_usb_link((STEREOLABS_USB_VENDOR_ID, ZED_MINI_USB_PRODUCT_ID), sysfs_root)
    assert not link.present
    assert link.link_speed_mbps is None


def test_a_host_with_no_usb_tree_is_not_an_error(tmp_path: Path) -> None:
    """An absent sysfs root reports the camera missing rather than raising."""
    link = probe_usb_link(
        (STEREOLABS_USB_VENDOR_ID, ZED_MINI_USB_PRODUCT_ID), tmp_path / "nothing-here"
    )
    assert not link.present


def test_the_default_usb_root_is_the_path_the_kernel_publishes_devices_under() -> None:
    """The probe's default root is pinned, because being wrong is indistinguishable here.

    A root nothing can be read from is a legitimate answer — it is what a bench with no
    USB tree looks like — so from inside the probe, one wrong character and an empty
    machine produce the same `present=False`. The cost is not a failing test: it is a
    deferral that names "no camera is enumerated" for a camera sitting on the bus, and
    an operator sent to check a cable that was never the problem.
    """
    assert Path(_KERNEL_USB_DEVICES_PATH) == USB_SYSFS_ROOT


@pytest.mark.skipif(
    not _SYSFS_MOUNT.is_dir(),
    reason="this host publishes no sysfs at all, so there is no kernel USB tree for the "
    "probe's default root to be checked against",
)
def test_the_default_usb_root_enumerates_this_hosts_own_devices() -> None:
    """The pinned root is a real USB tree on this machine, not merely a plausible string.

    Held against the kernel rather than against the constant, so a path that exists and
    holds something else fails here too. `idVendor` is the attribute the probe matches
    on, so its presence is what makes the tree the one the probe can work in.
    """
    entries = sorted(USB_SYSFS_ROOT.iterdir())
    assert any((entry / "idVendor").is_file() for entry in entries)
