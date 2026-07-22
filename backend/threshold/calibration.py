"""The per-joint base threshold thr0 — the WP-2C-03 calibration contract this package consumes.

WP-2C-03 is the human-assisted calibration wizard (SHAPE-HG): it collects residual max/sigma over
collision-free trajectories and emits a per-joint threshold [Nm] a human has judged. It owns no
code, so WP-2C-04 consumes its output as data, not by import. This type is the frozen carrier of
that data plus the band invariant the contract guarantees, checked at the point WP-2C-04 consumes
it: every base threshold sits in [10 x LSB, effort limit] per joint. A value below the floor would
fire on quantisation noise (FR-SAF-019); above the ceiling it could never be reached, leaving that
joint's detection dead (WP-2C-03 acceptance ②/③). Refused here rather than clamped, so a
mis-calibrated threshold cannot silently reach the residual comparison.

`literature_default()` is the FR-SAF-020 starting point (0.1 x effort). It is explicitly NOT an
OpenArm-measured value; a caller that has run WP-2C-03 passes the measured vector to
`from_calibration()` instead.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.threshold.constants import (
    JOINT_EFFORT_LIMITS_NM,
    N_ARM_JOINTS,
    THRESHOLD_DEFAULT_NM,
    THRESHOLD_MIN_NM,
)
from backend.threshold.errors import ThresholdConfigError


@dataclass(frozen=True)
class ThresholdCalibration:
    """The calibrated per-joint base threshold thr0 [Nm], validated to the contract band.

    Attributes:
        thr0: Per-joint base threshold [Nm], width `N_ARM_JOINTS`, joint1..joint7. Each element is
            the detection threshold in STATIC mode and the constant term of every scaled mode.
    """

    thr0: tuple[float, ...]

    def __post_init__(self) -> None:
        """Refuse a base-threshold vector of the wrong width or outside the [10 x LSB, effort] band.

        Raises:
            ThresholdConfigError: If `thr0` is not `N_ARM_JOINTS` wide, or any element is below its
                per-joint floor (10 x LSB) or above its URDF effort ceiling.
        """
        if len(self.thr0) != N_ARM_JOINTS:
            raise ThresholdConfigError(
                f"thr0 must be {N_ARM_JOINTS} joints wide, got {len(self.thr0)}"
            )
        for joint, value in enumerate(self.thr0):
            floor = THRESHOLD_MIN_NM[joint]
            ceiling = JOINT_EFFORT_LIMITS_NM[joint]
            if not floor <= float(value) <= ceiling:
                raise ThresholdConfigError(
                    f"joint{joint + 1} threshold {value} Nm is outside the contract band "
                    f"[{floor:.4g}, {ceiling:.4g}] Nm (10 x LSB floor, effort-limit ceiling)"
                )

    @classmethod
    def literature_default(cls) -> ThresholdCalibration:
        """Return the FR-SAF-020 literature starting point (0.1 x effort), not a measured value."""
        return cls(thr0=THRESHOLD_DEFAULT_NM)

    @classmethod
    def from_calibration(cls, thr0: tuple[float, ...]) -> ThresholdCalibration:
        """Return a calibration from a WP-2C-03 measured per-joint threshold vector.

        Args:
            thr0: Per-joint base threshold [Nm] the calibration wizard produced.

        Returns:
            (ThresholdCalibration) The validated calibration.
        """
        return cls(thr0=tuple(float(value) for value in thr0))
