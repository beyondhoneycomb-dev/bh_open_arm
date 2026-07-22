"""Pose sanity (`FR-TEL-038`): a `det ≈ 0` or non-finite frame is discarded, not passed.

A received VR pose reaches the robot as a base-frame rotation matrix. A rotation
must be a proper rotation (`det = +1`, `05` §2.8); a matrix whose determinant is
within `1e-6` of zero is a collapsed, non-invertible frame, and any NaN or infinite
element is a corrupt frame. Either one, driven through IK, produces a wild joint
command — so the sanity filter discards the frame and holds the last pose that
passed, exactly as the upstream `safe_mat_update` does.

The filter owns the last valid pose. When the very first pose is insane there is no
prior pose to fall back to, so it reports no valid pose and the gate holds at its
seed pose; the filter never fabricates one.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.teleop.safety_gate.constants import ROTATION_DET_ABS_TOL
from backend.teleop.safety_gate.pose import EEPose, determinant, is_finite_pose


def is_pose_sane(pose: EEPose, det_abs_tol: float = ROTATION_DET_ABS_TOL) -> bool:
    """Report whether a pose is a usable frame.

    Args:
        pose: The received pose.
        det_abs_tol: The determinant magnitude at or below which the rotation is
            treated as degenerate (`FR-TEL-038`, default `1e-6`).

    Returns:
        (bool) True only when every element is finite and the rotation determinant
        is not within `det_abs_tol` of zero.
    """
    if not is_finite_pose(pose):
        return False
    return abs(determinant(pose.rotation)) > det_abs_tol


@dataclass(frozen=True)
class SanityResult:
    """The outcome of filtering one received pose.

    Attributes:
        pose: The pose the gate should use — the received pose when accepted, the
            retained last-valid pose when discarded, or None when a pose was
            discarded before any valid pose had ever been seen.
        accepted: Whether the received pose passed the sanity check.
    """

    pose: EEPose | None
    accepted: bool


class PoseSanityFilter:
    """Discards degenerate/non-finite poses and retains the last valid one (`FR-TEL-038`).

    Ownership: holds the last pose that passed the sanity check. `accept` returns a
    `SanityResult` and never raises on a bad pose — a corrupt frame is an expected
    input on a noisy link, not an error — so the caller always has a pose (or an
    explicit None) to act on. One instance per teleop arm.
    """

    def __init__(self, det_abs_tol: float = ROTATION_DET_ABS_TOL) -> None:
        """Create a filter that has not yet seen a valid pose.

        Args:
            det_abs_tol: The degeneracy tolerance passed to `is_pose_sane`.
        """
        self._det_abs_tol = det_abs_tol
        self._last_valid: EEPose | None = None

    @property
    def last_valid(self) -> EEPose | None:
        """The most recent pose that passed, or None before any has."""
        return self._last_valid

    def seed(self, pose: EEPose) -> None:
        """Prime the filter with a known-good pose (the measured pose at engage).

        Args:
            pose: A pose taken as the initial last-valid, so the first discard has
                something to retain.
        """
        self._last_valid = pose

    def accept(self, pose: EEPose) -> SanityResult:
        """Accept a received pose or discard it, retaining the last valid pose.

        Args:
            pose: The received pose.

        Returns:
            (SanityResult) The accepted pose and `accepted=True`, or the retained
            last-valid pose (or None) and `accepted=False` when discarded.
        """
        if is_pose_sane(pose, self._det_abs_tol):
            self._last_valid = pose
            return SanityResult(pose=pose, accepted=True)
        return SanityResult(pose=self._last_valid, accepted=False)
