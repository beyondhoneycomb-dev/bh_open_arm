"""Real-camera enumeration — the deferred, hardware-only half of WP-0B-08.

Acceptance ①②③ (enumerate real cameras, detect a USB2 fallback, record controller
membership from the live bus) can only run against physical cameras, which this dev
host does not have. This module is therefore the honest boundary: it probes for the
enumeration backends and, when they or the cameras are absent, raises
`HardwareUnavailableError` with a reason rather than fabricating a descriptor. The
`enumerate_cameras` result — real descriptors — feeds the very calculators the
synthetic tests already exercise, so nothing downstream is stubbed, only the source.

Heavy backends (`pyrealsense2`, `pyudev`) are imported lazily inside the functions:
importing at module load would make the whole package unimportable on the light lane,
where those wheels are not installed.
"""

from __future__ import annotations

import importlib.util

from backend.camera.descriptor import CameraDescriptor

_REALSENSE_MODULE = "pyrealsense2"
_UDEV_MODULE = "pyudev"
_OPENCV_MODULE = "cv2"


class HardwareUnavailableError(RuntimeError):
    """Real-camera enumeration cannot run: a backend or a physical camera is absent."""


def backend_availability() -> dict[str, bool]:
    """Report which enumeration backends are importable on this host.

    Uses `find_spec` rather than importing, so probing never drags a heavy wheel in.

    Returns:
        (dict[str, bool]) Backend module name to whether it is importable.
    """
    return {
        module: importlib.util.find_spec(module) is not None
        for module in (_REALSENSE_MODULE, _UDEV_MODULE, _OPENCV_MODULE)
    }


def real_enumeration_supported() -> tuple[bool, str]:
    """Report whether real enumeration can run here, and why not when it cannot.

    RealSense enumeration and udev-symlink resolution both need their backends; a
    missing one means the live path is unavailable regardless of attached cameras.

    Returns:
        (tuple[bool, str]) `(supported, reason)`; reason is empty when supported.
    """
    available = backend_availability()
    missing = [module for module in (_REALSENSE_MODULE, _UDEV_MODULE) if not available[module]]
    if missing:
        return False, f"enumeration backend(s) not installed: {', '.join(missing)}"
    return True, ""


def enumerate_cameras() -> tuple[CameraDescriptor, ...]:
    """Enumerate physically attached cameras into descriptors (`06` FR-CAM-002).

    Returns:
        (tuple[CameraDescriptor, ...]) One descriptor per attached camera.

    Raises:
        HardwareUnavailableError: When an enumeration backend or the cameras are absent.
            This is what keeps the deferred acceptance honest — no cameras means no
            green, it means a skip with this reason.
    """
    supported, reason = real_enumeration_supported()
    if not supported:
        raise HardwareUnavailableError(reason)
    # The live RealSense/udev/OpenCV enumeration lands here once a rig exists; until
    # then the guard above makes the deferred acceptance skip rather than fabricate.
    raise HardwareUnavailableError(
        "enumeration backends present but live capture is unverified without a real "
        "camera set; supply a real capture to backend.camera.reverify instead"
    )
