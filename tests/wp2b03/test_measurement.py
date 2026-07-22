"""WP-2B-03 measurement model: width guards and the SYNTHETIC generator's honesty properties.

A pose or measured torque of the wrong width is refused. The synthetic generator stamps the
SYNTHETIC basis, equals the model at zero deviation, and refuses a malformed deviation grid —
the properties that keep a synthetic grid from being mistaken for a real one.
"""

from __future__ import annotations

import pytest

from backend.gravity import GravityBackend
from backend.gravity_verify import MeasurementBasis, synthesize_measurements
from backend.gravity_verify.errors import GravityVerifyError
from backend.gravity_verify.measurement import PoseMeasurement


def test_pose_measurement_refuses_wrong_pose_width() -> None:
    """A pose that is not seven joints wide is refused."""
    with pytest.raises(GravityVerifyError, match="pose must have 7"):
        PoseMeasurement(q=(0.0, 0.0), tau_meas=(0.0,) * 7, basis=MeasurementBasis.REAL)


def test_pose_measurement_refuses_wrong_torque_width() -> None:
    """A measured torque that is not seven joints wide is refused."""
    with pytest.raises(GravityVerifyError, match="measured torque must have 7"):
        PoseMeasurement(q=(0.0,) * 7, tau_meas=(0.0, 0.0), basis=MeasurementBasis.REAL)


def test_synthesize_stamps_synthetic_basis(
    backend: GravityBackend, pose_grid: tuple[tuple[float, ...], ...]
) -> None:
    """Every generated measurement is stamped SYNTHETIC."""
    grid = synthesize_measurements(pose_grid, backend)
    assert all(m.basis is MeasurementBasis.SYNTHETIC for m in grid)


def test_synthesize_zero_deviation_equals_model(
    backend: GravityBackend, pose_grid: tuple[tuple[float, ...], ...]
) -> None:
    """At zero deviation the measured torque equals the modelled gravity."""
    grid = synthesize_measurements(pose_grid, backend)
    for measurement in grid:
        assert measurement.tau_meas == pytest.approx(backend.tau_grav(measurement.q))


def test_synthesize_refuses_wrong_deviation_count(
    backend: GravityBackend, pose_grid: tuple[tuple[float, ...], ...]
) -> None:
    """A deviation grid with the wrong number of rows is refused."""
    with pytest.raises(GravityVerifyError, match="one row per pose"):
        synthesize_measurements(pose_grid, backend, ((0.0,) * 7,))


def test_synthesize_refuses_wrong_deviation_width(
    backend: GravityBackend, pose_grid: tuple[tuple[float, ...], ...]
) -> None:
    """A deviation row that is not seven wide is refused."""
    bad = tuple((0.0, 0.0) for _ in pose_grid)
    with pytest.raises(GravityVerifyError, match="deviation row"):
        synthesize_measurements(pose_grid, backend, bad)
