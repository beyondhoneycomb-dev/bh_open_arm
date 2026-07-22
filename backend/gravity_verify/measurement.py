"""The measured-torque pose grid, its basis, and the synthetic generator used to prove machinery.

A `PoseMeasurement` pairs a static pose with the joint torque measured while the arm is held
there (WP-2B-03 input: `use_velocity_and_torque=true`, torque-ON). The real grid needs a
torque-ON rig and an operator to align and hold each pose, so it is deferred on this host.

What runs here is the machinery on SYNTHETIC measurements. The generator is deliberately built
so it cannot self-approve: a synthetic measurement is the modelled gravity plus an *explicit*
per-joint deviation the caller supplies, and it is stamped `MeasurementBasis.SYNTHETIC`. A
zero-deviation grid gives a zero residual — a tautology, useful only to prove the arithmetic —
and every synthetic grid is provisional by construction, so a synthetic run can never stand in
for a real PG-FRIC-001 preceding measurement (THE ONE RULE).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from backend.gravity.backend import GravityBackend
from backend.gravity_verify.constants import ARM_JOINT_COUNT
from backend.gravity_verify.errors import GravityVerifyError


class MeasurementBasis(Enum):
    """Where a measured torque came from.

    SYNTHETIC is generated on this host to exercise the residual and anomaly math; a
    SYNTHETIC-basis run is always provisional. REAL is a torque-ON pose-grid capture supplied
    through the re-verification fixture hook and is the only basis that yields a PG-FRIC-001
    preceding verdict.
    """

    SYNTHETIC = "synthetic-measurements"
    REAL = "real-pose-grid"


@dataclass(frozen=True)
class PoseMeasurement:
    """One held pose and the joint torque measured there.

    Attributes:
        q: The arm's seven joint angles, v2 convention, radians.
        tau_meas: The seven measured joint torques at that pose, Nm, joint1..joint7 order.
        basis: Where `tau_meas` came from; a synthetic measurement never reads as real.
    """

    q: tuple[float, ...]
    tau_meas: tuple[float, ...]
    basis: MeasurementBasis

    def __post_init__(self) -> None:
        """Refuse a pose or measurement of the wrong width.

        Raises:
            GravityVerifyError: If `q` or `tau_meas` is not `ARM_JOINT_COUNT` wide.
        """
        if len(self.q) != ARM_JOINT_COUNT:
            raise GravityVerifyError(f"pose must have {ARM_JOINT_COUNT} angles, got {len(self.q)}")
        if len(self.tau_meas) != ARM_JOINT_COUNT:
            raise GravityVerifyError(
                f"measured torque must have {ARM_JOINT_COUNT} entries, got {len(self.tau_meas)}"
            )


def grid_basis(grid: Sequence[PoseMeasurement]) -> MeasurementBasis:
    """Return the single basis a grid is on, refusing an empty or mixed-basis grid.

    A grid mixing a real capture with synthetic fill would let a synthetic row hide inside a
    result read as real, so a mixed grid is refused rather than silently downgraded.

    Args:
        grid: The pose/measurement grid.

    Returns:
        (MeasurementBasis) The basis shared by every measurement.

    Raises:
        GravityVerifyError: On an empty grid or one whose measurements disagree on basis.
    """
    if not grid:
        raise GravityVerifyError("a verification grid must hold at least one measurement")
    bases = {measurement.basis for measurement in grid}
    if len(bases) != 1:
        raise GravityVerifyError(
            "a verification grid must be all-real or all-synthetic, not a mix "
            f"(found {sorted(basis.value for basis in bases)})"
        )
    return next(iter(bases))


def synthesize_measurements(
    poses: Sequence[Sequence[float]],
    backend: GravityBackend,
    deviations: Sequence[Sequence[float]] | None = None,
) -> tuple[PoseMeasurement, ...]:
    """Build a SYNTHETIC measurement grid: modelled gravity plus an explicit per-joint deviation.

    The deviation is what makes this honest rather than circular. With `deviations=None` every
    measurement equals the model, so the residual is zero — a tautology that proves only the
    arithmetic. To exercise a fingerprint (a shoulder sign error, a wrist mass error) the caller
    supplies a non-zero deviation grid, and the residual then equals that deviation exactly.
    Either way the result is stamped SYNTHETIC, so it stays provisional and never becomes a real
    verdict (THE ONE RULE — a synthetic-log run is never presented as a real PG-FRIC-001 pass).

    Args:
        poses: The static poses, each seven joint angles in the v2 convention, radians.
        backend: The WP-2B-02 gravity backend the modelled torque is read from.
        deviations: Optional per-pose per-joint additive torque, Nm, representing a hypothesised
            model error. None means zero deviation (measurement equals model).

    Returns:
        (tuple[PoseMeasurement, ...]) The synthetic grid, one entry per pose.

    Raises:
        GravityVerifyError: If a deviation row is supplied with the wrong width or count.
    """
    if deviations is not None and len(deviations) != len(poses):
        raise GravityVerifyError(
            f"deviation grid must have one row per pose ({len(poses)}), got {len(deviations)}"
        )
    measurements: list[PoseMeasurement] = []
    for index, pose in enumerate(poses):
        q = tuple(float(angle) for angle in pose)
        model = backend.tau_grav(q)
        deviation = _deviation_row(deviations, index)
        tau_meas = tuple(model[joint] + deviation[joint] for joint in range(ARM_JOINT_COUNT))
        measurements.append(
            PoseMeasurement(q=q, tau_meas=tau_meas, basis=MeasurementBasis.SYNTHETIC)
        )
    return tuple(measurements)


def _deviation_row(deviations: Sequence[Sequence[float]] | None, index: int) -> tuple[float, ...]:
    """Return the deviation vector for pose `index`, zero-filled when none was supplied.

    Raises:
        GravityVerifyError: If a supplied deviation row is not `ARM_JOINT_COUNT` wide.
    """
    if deviations is None:
        return (0.0,) * ARM_JOINT_COUNT
    row = tuple(float(value) for value in deviations[index])
    if len(row) != ARM_JOINT_COUNT:
        raise GravityVerifyError(
            f"deviation row {index} must have {ARM_JOINT_COUNT} entries, got {len(row)}"
        )
    return row
