"""Per-camera depth toggle and the `{cam}_depth` (H, W, 1) uint16 shape (WP-3B-03).

`06` §2.4/§2.5 (FR-CAM-038): depth is an *optional, per-camera* sibling of the RGB
stream, emitted only when the camera declares the capability and its `use_depth` is on.
It is never forced — a depth-capable camera stays RGB-only until its slot is toggled on,
so depth is never an implicit policy input (`02b` §6.2 WP-3B-03 ③).

Nothing here is device-specific. A slot is depth-capable because `CTR-CAM@v1` says its
capabilities include DEPTH, and the frame is well-formed because `CTR-PRIM@v1` fixes the
DEPTH frame type at one channel of uint16 — neither statement names a camera family, and
which families the *runtime* can actually drive is `version_gate`'s question, not this
module's.

Two facts are consumed from the frozen contracts and restated nowhere:

* the depth channel count and element dtype, via `constants`, which derives both from
  `CTR-PRIM@v1` for this package;
* the depth capability and the dataset depth key — `CTR-CAM@v1` `CameraSpec.has_depth`
  and `dataset_depth_key()`; a slot's depth feature key is the registry's, not a
  string this module assembles.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from backend.sensing.depth.constants import DEPTH_FRAME_CHANNELS, DEPTH_FRAME_DTYPE
from contracts.camera_registry import CameraRegistry, CameraSpec
from contracts.prim import CameraSlotKey


class DepthToggleError(ValueError):
    """Raised when depth is toggled on for a camera that cannot emit it.

    A camera whose `CTR-CAM@v1` capabilities omit DEPTH cannot be depth-enabled, and
    asking for it is a configuration error, not a runtime `OA-*` condition.
    """


class DepthShapeError(ValueError):
    """Raised when a depth frame is not the contract's `(H, W, 1)` uint16 shape."""


@dataclass(frozen=True)
class DepthToggles:
    """The camera slots whose `use_depth` is on for one collection session.

    A slot absent from `enabled` is RGB-only; the empty default is every camera
    RGB-only, which is what keeps depth from being an implicit policy input
    (`02b` §6.2 WP-3B-03 ③).

    Attributes:
        enabled: Slot-key strings with depth toggled on.
    """

    enabled: frozenset[str]

    def is_enabled(self, slot: CameraSlotKey) -> bool:
        """Whether depth is toggled on for this slot."""
        return slot.value in self.enabled

    @property
    def any_enabled(self) -> bool:
        """Whether any camera has depth toggled on this session."""
        return bool(self.enabled)


def resolve_depth_toggles(
    registry: CameraRegistry, enabled: Iterable[CameraSlotKey]
) -> DepthToggles:
    """Build the session's depth toggles, rejecting depth on a non-depth camera.

    Args:
        registry: The registered cameras (`CTR-CAM@v1`).
        enabled: Slots to toggle depth on.

    Returns:
        (DepthToggles) The validated per-camera toggle set.

    Raises:
        CameraRegistryError: If a named slot is not registered.
        DepthToggleError: If a registered slot lacks the DEPTH capability.
    """
    slots: set[str] = set()
    for slot in enabled:
        spec = registry.get(slot)
        if not spec.has_depth:
            raise DepthToggleError(
                f"camera {slot.value!r} has no depth capability in CTR-CAM@v1; depth cannot "
                "be toggled on for it (06 §2.5)"
            )
        slots.add(slot.value)
    return DepthToggles(frozenset(slots))


def depth_feature_shape(spec: CameraSpec) -> tuple[int, int, int]:
    """Return the `{cam}_depth` array shape `(height, width, 1)` for a camera.

    Args:
        spec: A configured depth-capable camera.

    Returns:
        (tuple) `(height, width, 1)`.

    Raises:
        DepthToggleError: If the camera has no depth capability.
        DepthShapeError: If the camera's geometry is not yet configured.
    """
    if not spec.has_depth:
        raise DepthToggleError(
            f"camera {spec.slot.value!r} has no depth capability; it emits no depth key"
        )
    if spec.width is None or spec.height is None:
        raise DepthShapeError(
            f"camera {spec.slot.value!r} has no width/height; its depth shape is undefined "
            "until it is configured (CTR-CAM@v1)"
        )
    return (spec.height, spec.width, DEPTH_FRAME_CHANNELS)


def depth_dataset_key(spec: CameraSpec) -> str:
    """Return the LeRobot depth feature key (`observation.images.<slot>_depth`).

    Delegates to `CTR-CAM@v1` so the key is the registry's derivation, not a string
    assembled here.

    Args:
        spec: A depth-capable camera.

    Returns:
        (str) The dataset depth feature key.

    Raises:
        DepthToggleError: If the camera has no depth capability.
    """
    key = spec.dataset_depth_key()
    if key is None:
        raise DepthToggleError(
            f"camera {spec.slot.value!r} has no depth capability; it has no depth dataset key"
        )
    return key


def validate_depth_frame(spec: CameraSpec, frame: NDArray[np.uint16]) -> None:
    """Validate a depth frame against the camera's contract shape and dtype.

    Args:
        spec: The camera the frame is claimed to belong to.
        frame: The depth array to check.

    Raises:
        DepthToggleError: If the camera has no depth capability.
        DepthShapeError: If the frame is not `(height, width, 1)` uint16.
    """
    expected_shape = depth_feature_shape(spec)
    if frame.shape != expected_shape:
        raise DepthShapeError(
            f"camera {spec.slot.value!r} depth frame shape {frame.shape!r} != "
            f"expected {expected_shape!r} (H, W, 1)"
        )
    if frame.dtype != DEPTH_FRAME_DTYPE:
        raise DepthShapeError(
            f"camera {spec.slot.value!r} depth frame dtype {frame.dtype!r} != "
            f"expected {DEPTH_FRAME_DTYPE!r} (uint16 millimetres)"
        )
