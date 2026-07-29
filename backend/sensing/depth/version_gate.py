"""LeRobot depth-backend gate: block collection start when depth outruns the runtime.

`06` §2.4 (FR-CAM-083, `02b` §6.2 WP-3B-03 ①): whether the depth pipeline exists is
decided by *API presence*, not a parsed version string. LeRobot 0.5.1 ships depth only
through synchronous `read_depth`; v0.6.0 adds `async_read_depth` and `read_latest_depth`,
which are the record/preview path the collection loop needs.

Two independent things can be missing, and collapsing them hides the more serious one:

* LeRobot ships no camera class for the attached family, so the camera cannot be opened
  at all — `DepthBackendMissingError`;
* the class exists but predates the v0.6.0 depth API, so it opens and records no depth
  key while the operator believes depth is on — `DepthApiMissingError`.

Both block start, so both derive from `DepthStartBlockedError` and a caller that only
asks "can this session start?" catches the base.

The family is a required argument. A default would mean one family silently, and a gate
that probes the class for a camera nobody attached returns a green describing a
different rig — which on this bench is exactly what happens, since the fitted camera is
a ZED and the class that would answer is the RealSense one.
"""

from __future__ import annotations

import importlib
from typing import Any

from backend.sensing.depth.constants import (
    DEPTH_ASYNC_READ_METHOD,
    DEPTH_LATEST_READ_METHOD,
    LEROBOT_DEPTH_CAMERA_CLASS,
    DepthDevice,
)
from backend.sensing.depth.toggle import DepthToggles


class DepthStartBlockedError(RuntimeError):
    """Raised when depth is enabled but the runtime cannot deliver it.

    The collection-start block of `02b` §6.2 WP-3B-03 ①: a hard refusal, not a degraded
    acceptance, because a started session would record no depth key while the operator
    believes depth is on.
    """


class DepthBackendMissingError(DepthStartBlockedError):
    """Raised when the installed LeRobot ships no camera class for the depth family."""


class DepthApiMissingError(DepthStartBlockedError):
    """Raised when the family's camera class predates the v0.6.0 depth record API."""


# The refusal for a family LeRobot ships no camera class for, shared by the resolver and
# the start gate so the two cannot describe the same absence in different words.
_NO_BACKEND_REASON = (
    "the installed LeRobot has no camera class for {device!r}; it cannot be opened "
    "through LeRobot at all, so no depth can be recorded from it (FR-CAM-083)"
)


def depth_record_api_present(camera_class: Any) -> bool:
    """Report whether a camera class exposes the v0.6.0 async/latest depth API.

    Args:
        camera_class: The runtime camera class (or any object) to probe.

    Returns:
        (bool) True when both `async_read_depth` and `read_latest_depth` are present.
    """
    return hasattr(camera_class, DEPTH_ASYNC_READ_METHOD) and hasattr(
        camera_class, DEPTH_LATEST_READ_METHOD
    )


def lerobot_backend_exists(device: DepthDevice) -> bool:
    """Report whether the installed LeRobot ships any camera class for this family."""
    return LEROBOT_DEPTH_CAMERA_CLASS[device] is not None


def installed_depth_camera_class(device: DepthDevice) -> Any:
    """Return the installed LeRobot camera class that drives this depth family.

    Imported lazily so that merely importing the depth path does not pull the lerobot
    camera stack.

    Args:
        device: The depth camera family to resolve.

    Returns:
        (Any) The LeRobot camera class for that family.

    Raises:
        DepthBackendMissingError: If LeRobot ships no camera class for the family.
    """
    target = LEROBOT_DEPTH_CAMERA_CLASS[device]
    if target is None:
        raise DepthBackendMissingError(_NO_BACKEND_REASON.format(device=device.value))
    module_name, class_name = target
    return getattr(importlib.import_module(module_name), class_name)


def assert_depth_backend_exists(device: DepthDevice) -> None:
    """Block a family the installed LeRobot ships no camera class for.

    Answerable without a camera class in hand, which is why it is separate from the API
    probe: a class the caller supplies is evidence about that class, never about whether
    LeRobot can drive `device` at all.

    Args:
        device: The depth camera family to judge.

    Raises:
        DepthBackendMissingError: If LeRobot ships no camera class for the family.
    """
    if lerobot_backend_exists(device):
        return
    raise DepthBackendMissingError(_NO_BACKEND_REASON.format(device=device.value))


def installed_runtime_supports_depth(device: DepthDevice) -> bool:
    """Report whether the installed LeRobot can record depth from this family.

    A genuine probe of the runtime installed on this host, with no camera hardware
    involved: false when the family has no backend at all, and false when the backend
    predates the v0.6.0 depth API.

    Args:
        device: The depth camera family to probe.

    Returns:
        (bool) True only when a backend exists and carries the async/latest API.
    """
    if not lerobot_backend_exists(device):
        return False
    return depth_record_api_present(installed_depth_camera_class(device))


def assert_depth_startable(
    toggles: DepthToggles, device: DepthDevice, camera_class: Any = None
) -> None:
    """Block collection start when depth is enabled but the runtime cannot deliver it.

    The two blocks are ordered, and the order is part of the contract: backend existence
    is judged first and without consulting `camera_class`, so a family LeRobot cannot
    open is refused whatever class the caller hands in. A green obtained by supplying a
    healthy class would describe that class and not this rig.

    Args:
        toggles: The session's per-camera depth toggles.
        device: The depth camera family attached for this session.
        camera_class: The runtime camera class to judge; defaults to the installed class
            for `device` when None.

    Raises:
        DepthBackendMissingError: If depth is on and LeRobot has no backend for `device`.
        DepthApiMissingError: If depth is on and the class lacks the v0.6.0 depth API.
    """
    if not toggles.any_enabled:
        return
    assert_depth_backend_exists(device)
    probed = installed_depth_camera_class(device) if camera_class is None else camera_class
    if not depth_record_api_present(probed):
        raise DepthApiMissingError(
            f"depth is toggled on for {device.value!r} but the runtime camera class lacks "
            f"{DEPTH_ASYNC_READ_METHOD}/{DEPTH_LATEST_READ_METHOD} (LeRobot < 0.6.0); "
            "collection start is blocked (FR-CAM-083)"
        )
