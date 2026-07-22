"""Shared fixtures for the WP-2B-07 friction-identification acceptance tests.

The synthetic log and its identification are the expensive step (a forward dynamics pass per
sample), so they are built once at session scope and shared read-only. Every artefact here is a
frozen dataclass or a numpy array the tests only read, so sharing is safe.
"""

from __future__ import annotations

from typing import Any

import pytest

from backend.dynamics.provenance import Provenance
from backend.friction import (
    IdentificationResult,
    InverseDynamicsBasis,
    SyntheticLog,
    band_from_identification,
    build_friction_document,
    generate_synthetic_log,
    identify_friction,
    relative_error_table,
    separation_stats,
)
from backend.friction.seed import V1_SEED_FRICTION
from backend.gravity import Arm

_TEST_PROVENANCE = Provenance(
    source_repo="bh_open_arm",
    commit_sha="SYNTHETIC-NO-HARDWARE",
    path="backend/friction/friction.provisional.yaml",
    robot_version="2.0",
    identified_on="2026-07-22",
)


@pytest.fixture(scope="session")
def basis() -> InverseDynamicsBasis:
    """The right-arm inverse-dynamics basis (loads the committed v2 model once)."""
    return InverseDynamicsBasis(Arm.RIGHT)


@pytest.fixture(scope="session")
def synthetic(basis: InverseDynamicsBasis) -> SyntheticLog:
    """A synthetic excitation log with genuine v2 dynamics and known friction."""
    return generate_synthetic_log(basis)


@pytest.fixture(scope="session")
def result(basis: InverseDynamicsBasis, synthetic: SyntheticLog) -> IdentificationResult:
    """The identification of the shared synthetic log, warm-started from the v1 seed."""
    return identify_friction(synthetic.log, basis, V1_SEED_FRICTION)


@pytest.fixture(scope="session")
def document(result: IdentificationResult, synthetic: SyntheticLog) -> dict[str, Any]:
    """The full friction.yaml document built from the shared identification."""
    stats = separation_stats(result)
    band = band_from_identification(synthetic.log, result)
    rel_errors = relative_error_table(result.params())
    return build_friction_document(result, band, _TEST_PROVENANCE, stats, rel_errors)
