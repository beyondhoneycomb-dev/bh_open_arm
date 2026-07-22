"""The cartesian workspace virtual wall (`FR-TEL-036`): a base-frame box the EE is projected into.

`mink.ConfigurationLimit` constrains joint space; there is no cartesian box limit
anywhere upstream. This is it: a base-frame axis-aligned box of per-axis `min`/`max`.
An EE target outside the box is projected onto the nearest boundary face (each axis
clamped independently), which the gate commands instead of the out-of-bounds target,
and the violation is reported so the GUI/HMD can show the wall warning. A *persistent*
violation is a fault the gate escalates to a hold (`05` §4.3, S4 → S7); a single
projection keeps following.

The box is user-defined (`05` §5 parameter table) — there is no safe default extent,
so one must be supplied. The gate only ever reads it, so it is frozen.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.teleop.safety_gate.pose import EEPose, Vector3


@dataclass(frozen=True)
class WallProjection:
    """The outcome of projecting one EE target against the workspace box.

    Attributes:
        translation: The in-bounds translation to command — the input unchanged when
            it was already inside, or the boundary projection when it was outside.
        violated: Whether the input translation was outside the box on any axis.
    """

    translation: Vector3
    violated: bool


@dataclass(frozen=True)
class WorkspaceBox:
    """A base-frame axis-aligned keep-in box that projects an EE target onto its wall.

    Ownership: an immutable geometric definition the gate reads. It holds no runtime
    state; the persistence of a violation is counted by the gate, not here, so the
    box stays a pure function of a point.

    Attributes:
        min_corner: The per-axis lower bounds `(x, y, z)` in metres.
        max_corner: The per-axis upper bounds `(x, y, z)` in metres.
    """

    min_corner: Vector3
    max_corner: Vector3

    def __post_init__(self) -> None:
        """Reject a box whose lower bound is not below its upper bound on every axis.

        Raises:
            ValueError: If any axis has `min >= max`, which would be an empty or
                inverted box no point could be projected into.
        """
        for axis, (low, high) in enumerate(zip(self.min_corner, self.max_corner, strict=True)):
            if low >= high:
                raise ValueError(
                    f"workspace box axis {axis} has min {low} >= max {high}; "
                    "the keep-in box must have positive extent on every axis"
                )

    def contains(self, translation: Vector3) -> bool:
        """Report whether a translation lies inside the box (boundary inclusive).

        Args:
            translation: The EE position to test.

        Returns:
            (bool) True when every axis is within `[min, max]`.
        """
        return all(
            low <= value <= high
            for value, low, high in zip(translation, self.min_corner, self.max_corner, strict=True)
        )

    def project(self, translation: Vector3) -> WallProjection:
        """Project an EE target onto the box, reporting whether it was outside.

        Each axis is clamped independently to `[min, max]`, which is the projection
        onto the nearest boundary face for an axis-aligned box.

        Args:
            translation: The requested EE position.

        Returns:
            (WallProjection) The in-bounds position and the violation flag.
        """
        clamped = tuple(
            _clamp(value, low, high)
            for value, low, high in zip(translation, self.min_corner, self.max_corner, strict=True)
        )
        projected: Vector3 = clamped  # type: ignore[assignment]
        return WallProjection(translation=projected, violated=projected != translation)

    def project_pose(self, pose: EEPose) -> WallProjection:
        """Project a pose's translation onto the box, leaving its rotation untouched.

        Args:
            pose: The requested EE pose.

        Returns:
            (WallProjection) The projected translation and the violation flag.
        """
        return self.project(pose.translation)


def _clamp(value: float, low: float, high: float) -> float:
    """Clamp a scalar to `[low, high]`."""
    if value < low:
        return low
    if value > high:
        return high
    return value
