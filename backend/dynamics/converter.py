"""The v1->v2 joint-frame converter: joint2 +pi/2 zero shift and per-joint axis-sign normalisation.

This is the machinery FR-SAF-033 requires. A v1-derived dynamics model expresses joint
angles in the v1 zero convention; feeding those angles to a v2 model (or the reverse)
without this conversion puts a sin<->cos error into joint2's gravity term (spec 12 §2.6).
The converter is a pure function of its offset and sign vectors and carries no mutable
state, so WP-2B-02 can hold one instance for the whole gravity backend.

Positions carry the zero offset (pi/2 at joint2) plus the axis sign; velocities and torques
carry only the axis sign, because a zero-frame shift moves an angle's origin, not a rate or a
moment about the axis.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from backend.dynamics.constants import (
    ARM_JOINT_COUNT,
    IDENTITY_AXIS_SIGNS,
    J2_ZERO_SHIFT_RAD,
    JOINT2_INDEX,
)
from backend.dynamics.errors import DynamicsConversionError


def _zero_offsets() -> tuple[float, ...]:
    """Return the per-joint position zero offsets: +pi/2 at joint2, zero elsewhere."""
    offsets = [0.0] * ARM_JOINT_COUNT
    offsets[JOINT2_INDEX] = J2_ZERO_SHIFT_RAD
    return tuple(offsets)


def convert_joint2_angle(v1_angle: float) -> float:
    """Apply the joint2 +pi/2 zero shift to a single v1 joint2 angle (FR-SAF-033).

    This is the narrow, always-true core of the conversion: joint2 has no axis flip, so its
    v2 angle is exactly the v1 angle plus pi/2, and `V1_JOINT2_RANGE_RAD` maps onto
    `V2_JOINT2_RANGE_RAD` under it.

    Args:
        v1_angle: A joint2 angle in the v1 zero convention, radians.

    Returns:
        (float) The same angle in the v2 convention.
    """
    return v1_angle + J2_ZERO_SHIFT_RAD


@dataclass(frozen=True)
class JointFrameConverter:
    """A stateless v1<->v2 joint-frame map for one arm.

    Attributes:
        axis_signs: Per-joint +/-1 factor bringing a v1 joint's positive-rotation direction
            onto the v2 `joint_axes.yaml` reference. joint2 is +1: its correction is the
            zero offset, not a flip.
    """

    axis_signs: tuple[int, ...] = IDENTITY_AXIS_SIGNS

    def __post_init__(self) -> None:
        """Validate the sign-vector width and that every entry is exactly +1 or -1.

        Raises:
            DynamicsConversionError: On a wrong-width vector or a non-unit sign.
        """
        if len(self.axis_signs) != ARM_JOINT_COUNT:
            raise DynamicsConversionError(
                f"axis_signs must have {ARM_JOINT_COUNT} entries, got {len(self.axis_signs)}"
            )
        for index, sign in enumerate(self.axis_signs):
            if sign not in (1, -1):
                raise DynamicsConversionError(f"axis_signs[{index}] must be +1 or -1, got {sign!r}")

    @classmethod
    def v2_default(cls) -> JointFrameConverter:
        """Return the default v1->v2 converter: joint2 +pi/2 shift, no axis flips.

        This is the converter WP-2B-02 consumes. A v1 asset whose axis signs differ from the
        v2 reference builds its own converter with an explicit `axis_signs`.
        """
        return cls()

    def _checked(self, values: Sequence[float]) -> tuple[float, ...]:
        """Return `values` as a float tuple, refusing a wrong-width joint vector.

        Raises:
            DynamicsConversionError: If the vector is not `ARM_JOINT_COUNT` wide.
        """
        vector = tuple(float(value) for value in values)
        if len(vector) != ARM_JOINT_COUNT:
            raise DynamicsConversionError(
                f"joint vector must have {ARM_JOINT_COUNT} entries, got {len(vector)}"
            )
        return vector

    def convert_angles(self, v1_angles: Sequence[float]) -> tuple[float, ...]:
        """Map v1 joint angles to v2: axis sign then the joint2 +pi/2 zero shift.

        Args:
            v1_angles: One arm's joint angles in the v1 zero convention, radians.

        Returns:
            (tuple[float, ...]) The same pose in the v2 convention.

        Raises:
            DynamicsConversionError: On a wrong-width vector.
        """
        checked = self._checked(v1_angles)
        offsets = _zero_offsets()
        return tuple(self.axis_signs[j] * checked[j] + offsets[j] for j in range(ARM_JOINT_COUNT))

    def invert_angles(self, v2_angles: Sequence[float]) -> tuple[float, ...]:
        """Map v2 joint angles back to the v1 convention — the inverse of `convert_angles`.

        Evaluating a v1 gravity model needs v1 angles; given a v2 pose this recovers them so
        the v1 model is evaluated at the correct argument rather than at a shifted one.

        Args:
            v2_angles: One arm's joint angles in the v2 convention, radians.

        Returns:
            (tuple[float, ...]) The same pose in the v1 convention.

        Raises:
            DynamicsConversionError: On a wrong-width vector.
        """
        checked = self._checked(v2_angles)
        offsets = _zero_offsets()
        # A +/-1 sign is its own inverse, so undo the offset first, then re-apply the sign.
        return tuple(self.axis_signs[j] * (checked[j] - offsets[j]) for j in range(ARM_JOINT_COUNT))

    def convert_velocities(self, v1_velocities: Sequence[float]) -> tuple[float, ...]:
        """Map v1 joint velocities to v2 (axis sign only; a zero shift does not move a rate).

        Args:
            v1_velocities: One arm's joint velocities in the v1 convention, rad/s.

        Returns:
            (tuple[float, ...]) The same velocities in the v2 convention.

        Raises:
            DynamicsConversionError: On a wrong-width vector.
        """
        return self._apply_sign_only(v1_velocities)

    def convert_torques(self, v1_torques: Sequence[float]) -> tuple[float, ...]:
        """Map v1 joint torques to v2 (axis sign only; a zero shift does not move a moment).

        Args:
            v1_torques: One arm's joint torques in the v1 convention, Nm.

        Returns:
            (tuple[float, ...]) The same torques in the v2 convention.

        Raises:
            DynamicsConversionError: On a wrong-width vector.
        """
        return self._apply_sign_only(v1_torques)

    def _apply_sign_only(self, values: Sequence[float]) -> tuple[float, ...]:
        """Apply the per-joint axis sign with no zero offset (shared by rates and moments)."""
        checked = self._checked(values)
        return tuple(self.axis_signs[j] * checked[j] for j in range(ARM_JOINT_COUNT))
