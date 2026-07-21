"""Acceptance ③ — the load bites, and a no-load harness does not pass.

The interleaved measurement (OFF / same-process / separate-process, drift-shared) is
what makes this robust: a real load's same-process cycles are distinguishable from the
OFF cycles, and a no-load profile's are not. The GIL contribution (④) is computed as a
number regardless of the host's core count — whether the separate-process arm reduces
it depends on having a spare core, so this suite pins the computation, not a machine's
scheduling.

The interleaved runs are module-scoped fixtures so each profile is measured once.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from sim.harness.interleave import InterleavedMeasurement, run_interleaved
from sim.harness.load_profile import LoadProfile

_REAL = LoadProfile(5, 320, 240, 32 * 1024, 128 * 1024)
_NO_LOAD = LoadProfile(0, 320, 240, 0, 0)


def _measure(profile: LoadProfile, dataset_dir: str) -> InterleavedMeasurement:
    """Run one small interleaved measurement for the suite."""
    return run_interleaved(
        profile,
        target_hz=250.0,
        warmup=30,
        segment_len=12,
        repeats=18,
        dataset_dir=dataset_dir,
    )


@pytest.fixture(scope="module")
def real_measurement(tmp_path_factory: pytest.TempPathFactory) -> InterleavedMeasurement:
    """One interleaved measurement under a real load, shared across the module."""
    return _measure(_REAL, str(tmp_path_factory.mktemp("real")))


@pytest.fixture(scope="module")
def no_load_measurement(tmp_path_factory: pytest.TempPathFactory) -> InterleavedMeasurement:
    """One interleaved measurement under a no-load profile, shared across the module."""
    return _measure(_NO_LOAD, str(tmp_path_factory.mktemp("noload")))


def test_real_load_bites(real_measurement: InterleavedMeasurement) -> None:
    """A real load makes the same-process cycles distinguishable from idle, inflated up."""
    assert real_measurement.load_bite.distinguishable
    assert real_measurement.load_bite.cliffs_delta > 0.0
    same_median = float(np.median(real_measurement.same_process.samples))
    off_median = float(np.median(real_measurement.off.samples))
    assert same_median > off_median


def test_gil_contribution_is_computed_as_a_number(real_measurement: InterleavedMeasurement) -> None:
    """The GIL contribution (condition 4 minus condition 5) is a finite computed number (④)."""
    contribution = float(
        np.median(real_measurement.same_process.samples)
        - np.median(real_measurement.separate_process.samples)
    )
    assert math.isfinite(contribution)


def test_no_load_does_not_pass(no_load_measurement: InterleavedMeasurement) -> None:
    """A no-load profile is NOT distinguishable from idle — the instrument is not rigged."""
    assert not no_load_measurement.load_bite.distinguishable
    assert not no_load_measurement.gil_contribution.distinguishable


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
