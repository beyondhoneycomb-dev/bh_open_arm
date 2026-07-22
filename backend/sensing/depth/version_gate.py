"""LeRobot depth-API gate: block collection start when depth outruns the runtime.

`06` §2.4 (FR-CAM-083, `02b` §6.2 WP-3B-03 ①): whether the depth pipeline exists is
decided by *API presence*, not a parsed version string. LeRobot 0.5.1 ships depth
only through synchronous `read_depth`; v0.6.0 adds `async_read_depth` and
`read_latest_depth`, which are the record/preview path the collection loop needs.
When any camera has depth toggled on but the runtime camera class lacks those two
methods, collection start is blocked — otherwise the depth key silently never appears.

The RealSense camera class lives behind the lerobot camera stack; it is imported
lazily, and the gate accepts an injected class so the block is testable without the
real class (a stub missing the two methods stands in for a 0.5.1 runtime).
"""

from __future__ import annotations

from typing import Any

from backend.sensing.depth.constants import DEPTH_ASYNC_READ_METHOD, DEPTH_LATEST_READ_METHOD
from backend.sensing.depth.toggle import DepthToggles


class DepthStartBlockedError(RuntimeError):
    """Raised when depth is enabled but the runtime lacks the v0.6.0 depth API.

    This is the collection-start block of `02b` §6.2 WP-3B-03 ①: a hard refusal, not
    a degraded acceptance, because a started session would record no depth key while
    the operator believes depth is on.
    """


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


def installed_realsense_camera_class() -> Any:
    """Return the installed LeRobot RealSense camera class.

    Imported lazily so that merely importing the depth path does not pull the lerobot
    camera stack.

    Returns:
        (Any) The `RealSenseCamera` class from the installed lerobot.
    """
    from lerobot.cameras.realsense.camera_realsense import RealSenseCamera

    return RealSenseCamera


def installed_runtime_supports_depth() -> bool:
    """Report whether the installed LeRobot exposes the v0.6.0 depth record API.

    A genuine probe of the runtime actually installed on this host — True on v0.6.0,
    False on 0.5.1 — with no camera hardware involved.

    Returns:
        (bool) True when the installed RealSense class carries the async/latest API.
    """
    return depth_record_api_present(installed_realsense_camera_class())


def assert_depth_startable(toggles: DepthToggles, camera_class: Any = None) -> None:
    """Block collection start when depth is enabled but the runtime API is absent.

    Args:
        toggles: The session's per-camera depth toggles.
        camera_class: The runtime camera class to judge; defaults to the installed
            RealSense class when None.

    Raises:
        DepthStartBlockedError: If any camera has depth on and the class lacks the API.
    """
    if not toggles.any_enabled:
        return
    probed = installed_realsense_camera_class() if camera_class is None else camera_class
    if not depth_record_api_present(probed):
        raise DepthStartBlockedError(
            f"depth is toggled on but the runtime camera class lacks "
            f"{DEPTH_ASYNC_READ_METHOD}/{DEPTH_LATEST_READ_METHOD} (LeRobot < 0.6.0); "
            "collection start is blocked (FR-CAM-083)"
        )
