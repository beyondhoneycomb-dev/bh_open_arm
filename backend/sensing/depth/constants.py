"""Named domain tokens for the depth path (WP-3B-03, `06` §2.4).

The quantisation figures are deliberately absent here. `depth_min`, `depth_max`,
`shift`, `use_log`, the 12-bit quantum ceiling and the pixel format are the frozen
LeRobot v0.6.0 `DepthEncoderConfig` values; `encoding.py` imports them from
`lerobot.configs.video` at the one place they are used, so this platform owns no
second copy of the encoder grid (`06` §2.4).

What this module owns is the line between what depends on the depth *transport* and
what depends on the depth *device*. The transport — uint16 millimetres, one channel,
0 = no measurement — is fixed by `CTR-PRIM@v1` for the DEPTH frame type as such, not
per camera backend, so every calculator built on it (`encoding`, `fill_rate`,
`toggle`) is device-agnostic by construction. The device enters at exactly two points,
both named below: which LeRobot camera class can drive the sensor, and which vendor
SDK the live path needs.
"""

from __future__ import annotations

from enum import StrEnum

import numpy as np

from contracts.prim import FRAME_TYPE_CHANNELS, FRAME_TYPE_DTYPE, FrameType

# Derived from the one place they are defined (`CTR-PRIM@v1`) so no shape or dtype
# check downstream can drift from the contract.
DEPTH_FRAME_CHANNELS = FRAME_TYPE_CHANNELS[FrameType.DEPTH]
DEPTH_FRAME_DTYPE = np.dtype(FRAME_TYPE_DTYPE[FrameType.DEPTH])

# A depth pixel of 0 mm means "no measurement available", never "zero distance"
# (`06` §2.4, FR-CAM-038). This is a property of the transport above, not of how the
# depth was produced: a projector camera writes 0 where the pattern was not returned,
# a stereo camera writes 0 where the pair did not match, and the fraction of non-zero
# pixels carries the same meaning in both cases. The lossy log encoder does not
# preserve this sentinel, so it is the fill-rate and invalid-mask carrier — named here
# rather than written as a bare 0 at each site.
DEPTH_NO_MEASUREMENT_MM = 0

# The two methods whose presence *is* the v0.6.0 depth gate (`06` §2.4): 0.5.1 ships
# neither (depth only via synchronous `read_depth`), v0.6.0 adds both for the
# record/preview path. The gate is judged on these names, never on a parsed version
# string (FR-CAM-083, `02b` §6.2 WP-3B-03 ①).
DEPTH_ASYNC_READ_METHOD = "async_read_depth"
DEPTH_LATEST_READ_METHOD = "read_latest_depth"


class DepthDevice(StrEnum):
    """A depth camera family, named because runtime support differs per family.

    `06` §2.5 was written when the only depth-emitting LeRobot class was the RealSense
    one, and reads as though "depth camera" and "RealSense" were one word. They are
    two: a family is usable here only if LeRobot ships a camera class for it *and*
    that class carries the v0.6.0 depth API, and a single name cannot hold both facts
    while leaving either one falsifiable.

    `INTEL_REALSENSE` carries the same value as
    `backend.camera.descriptor.CameraType.INTEL_REALSENSE`. `STEREOLABS_ZED` has no
    counterpart there, so a ZED cannot presently be given a `CameraDescriptor` at all.
    """

    INTEL_REALSENSE = "intelrealsense"
    STEREOLABS_ZED = "stereolabs_zed"


# The LeRobot camera class that drives each family, as `(module, class name)`. None
# means the installed LeRobot ships no backend for that family, which is a stronger
# absence than a backend whose depth API is too old — the first cannot be opened at
# all, the second opens and silently records nothing. LeRobot v0.6.0's camera backends
# are opencv, reachy2_camera, realsense and zmq; no ZED is among them.
LEROBOT_DEPTH_CAMERA_CLASS: dict[DepthDevice, tuple[str, str] | None] = {
    DepthDevice.INTEL_REALSENSE: (
        "lerobot.cameras.realsense.camera_realsense",
        "RealSenseCamera",
    ),
    DepthDevice.STEREOLABS_ZED: None,
}

# The vendor SDK module each family's live path needs. Neither is a declared dependency
# of this platform, and they are not equally obtainable: `pyrealsense2` is a wheel on
# the index, while `pyzed` is not published at all — the Stereolabs ZED SDK installer
# generates it against the host's CUDA, so it can only appear after an operator installs
# that SDK on this machine.
DEPTH_SDK_MODULE: dict[DepthDevice, str] = {
    DepthDevice.INTEL_REALSENSE: "pyrealsense2",
    DepthDevice.STEREOLABS_ZED: "pyzed",
}

# USB identity of the depth camera fitted to this rig, so the deferral names something
# checkable instead of an assumption. The ZED exposes its stereo pair through the
# Stereolabs SDK rather than as a V4L2 node, which is why an enumeration keyed on
# `/dev/video*` does not merely come up empty — on this host those nodes belong to an
# unrelated UVC camera, and a keyed-on-V4L2 probe would bind that one instead.
STEREOLABS_USB_VENDOR_ID = "2b03"
ZED_MINI_USB_PRODUCT_ID = "f681"

# The `(vendor, product)` pair `usb_link` recognises each family by when it reports how
# the camera is attached. None means no identity is recorded and no link check runs for
# that family: Intel ships a different product id per RealSense model (D415, D435,
# D455, …) and none of them is fitted here, so one value written down would be a guess
# in the position of a measurement — which is the shape this module exists to avoid.
DEPTH_USB_ID: dict[DepthDevice, tuple[str, str] | None] = {
    DepthDevice.INTEL_REALSENSE: None,
    DepthDevice.STEREOLABS_ZED: (STEREOLABS_USB_VENDOR_ID, ZED_MINI_USB_PRODUCT_ID),
}
