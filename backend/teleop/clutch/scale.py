"""Relative-delta mapping with independent position and rotation scale (`FR-TEL-032`).

The follower target is the reference EE pose composed with the leader's motion since
grip, each channel scaled on its own factor:

    target_position = ref_ee_position + position_scale * (controller_position - ref)
    target_rotation = scale_rotation(controller_rotation_since_grip, rotation_scale)
                      applied on top of ref_ee_rotation

Position scale (`FR-TEL-033`, default 0.8) and rotation scale (`FR-TEL-029`, default
1.0) are separate parameters and never share a value: joint6's ±45° limit forces the
rotation channel to be narrowed without shrinking translation. Because the delta is
measured from the reference, a freshly re-captured reference yields a zero delta and the
target equals the reference EE pose — the re-grip no-jump invariant (`FR-TEL-031`).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from backend.teleop.clutch.clutch import PoseReference
from backend.teleop.clutch.constants import (
    POSITION_SCALE_DEFAULT,
    POSITION_SCALE_MAX,
    POSITION_SCALE_MIN,
    ROTATION_SCALE_DEFAULT,
    ROTATION_SCALE_MAX,
    ROTATION_SCALE_MIN,
)
from backend.teleop.clutch.rotation import (
    quat_conjugate,
    quat_multiply,
    quat_normalize,
    scale_rotation,
)


@dataclass(frozen=True, eq=False)
class PoseTarget:
    """A commanded EE pose produced by the mapping or the smoother.

    Attributes:
        position: Target EE position `(x, y, z)`.
        quaternion: Target EE orientation `(x, y, z, w)`, unit.
    """

    position: np.ndarray
    quaternion: np.ndarray


class DeltaScaler:
    """Maps a leader delta onto the follower with independent position/rotation scale.

    Stateless across ticks: every call is a pure function of the reference and the
    current controller pose, so one instance is shared by an arm's loop and the two
    scale factors are the only mutable configuration.
    """

    def __init__(
        self,
        position_scale: float = POSITION_SCALE_DEFAULT,
        rotation_scale: float = ROTATION_SCALE_DEFAULT,
    ) -> None:
        """Create a scaler with independent position and rotation factors.

        Args:
            position_scale: Multiplier on the translation delta (`FR-TEL-033`).
            rotation_scale: Multiplier on the rotation angle (`FR-TEL-029`), independent
                of `position_scale`.

        Raises:
            ValueError: If either factor is outside its adjustable range.
        """
        if not POSITION_SCALE_MIN <= position_scale <= POSITION_SCALE_MAX:
            raise ValueError(
                f"position scale {position_scale} outside "
                f"[{POSITION_SCALE_MIN}, {POSITION_SCALE_MAX}]"
            )
        if not ROTATION_SCALE_MIN <= rotation_scale <= ROTATION_SCALE_MAX:
            raise ValueError(
                f"rotation scale {rotation_scale} outside "
                f"[{ROTATION_SCALE_MIN}, {ROTATION_SCALE_MAX}]"
            )
        self._position_scale = position_scale
        self._rotation_scale = rotation_scale

    @property
    def position_scale(self) -> float:
        """The translation-delta multiplier."""
        return self._position_scale

    @property
    def rotation_scale(self) -> float:
        """The rotation-angle multiplier, independent of position scale."""
        return self._rotation_scale

    def target(
        self,
        reference: PoseReference,
        controller_position: np.ndarray,
        controller_quaternion: np.ndarray,
    ) -> PoseTarget:
        """Compose the scaled leader delta onto the reference EE pose.

        Args:
            reference: The pose pair latched at grip.
            controller_position: Current leader controller position `(x, y, z)`.
            controller_quaternion: Current leader controller orientation `(x, y, z, w)`.

        Returns:
            (PoseTarget) The follower EE target. Equals the reference EE pose exactly
            when the controller pose equals the reference (a just-captured reference).
        """
        controller_now = np.asarray(controller_position, dtype=float)
        position_delta = controller_now - reference.controller_position
        target_position = reference.ee_position + self._position_scale * position_delta

        rotation_delta = quat_multiply(
            quat_normalize(controller_quaternion),
            quat_conjugate(reference.controller_quaternion),
        )
        scaled_rotation = scale_rotation(rotation_delta, self._rotation_scale)
        target_quaternion = quat_normalize(quat_multiply(scaled_rotation, reference.ee_quaternion))

        return PoseTarget(position=target_position, quaternion=target_quaternion)
