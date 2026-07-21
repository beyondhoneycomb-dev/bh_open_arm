"""Acceptance ⑦⑧ — the deploy-target-capability axis enforces FR-INF-033/034.

The capability axis reuses the WP-ENV-02 guards named on each target in
`targets/matrix.yaml`. On Jetson Orin, GR00T synchronous inference above the 4.6 Hz
ceiling is blocked (FR-INF-034), and the `trt_full_pipeline` optimisation path is
blocked outright because TRT 10.3 cannot compile the backbone engine (FR-INF-033).
The suite also checks the axis does not over-block: async GR00T and a below-ceiling
rate on a target with no measured ceiling stay allowed.
"""

from __future__ import annotations

import pytest

from backend.policy_matrix import DatasetObsConfig, DeployRequest, build_matrix
from backend.policy_matrix.matrix import AXIS_CAPABILITY

_UNIMANUAL_24 = DatasetObsConfig(bimanual=False, use_velocity_and_torque=True)


@pytest.fixture(scope="module")
def matrix():  # type: ignore[no-untyped-def]
    """The calculator over the on-disk registry and target matrix."""
    return build_matrix()


def test_orin_groot_sync_over_ceiling_is_blocked(matrix) -> None:  # type: ignore[no-untyped-def]
    """⑦ — Orin + GR00T + sync above 4.6 Hz is blocked (FR-INF-034)."""
    deploy = DeployRequest(target_id="jetson_orin", mode="sync", fps=30)
    cell = matrix.evaluate(_UNIMANUAL_24, "groot", deploy)
    capability = [b for b in cell.blocks if b.axis == AXIS_CAPABILITY]
    assert [b.code for b in capability] == ["groot_sync_over_ceiling"]
    assert not cell.allowed


def test_orin_trt_full_pipeline_is_blocked(matrix) -> None:  # type: ignore[no-untyped-def]
    """⑧ — Orin + trt_full_pipeline is blocked (FR-INF-033)."""
    deploy = DeployRequest(
        target_id="jetson_orin", mode="async", optimization_path="trt_full_pipeline"
    )
    cell = matrix.evaluate(_UNIMANUAL_24, "groot", deploy)
    capability = [b for b in cell.blocks if b.axis == AXIS_CAPABILITY]
    assert "orin_trt_full_pipeline" in [b.code for b in capability]
    assert not cell.allowed


def test_orin_groot_async_is_not_over_blocked(matrix) -> None:  # type: ignore[no-untyped-def]
    """Async GR00T on Orin (24-dim) clears both axes — the block is not a blanket ban."""
    deploy = DeployRequest(target_id="jetson_orin", mode="async")
    cell = matrix.evaluate(_UNIMANUAL_24, "groot", deploy)
    assert cell.allowed


def test_sync_below_ceiling_is_allowed(matrix) -> None:  # type: ignore[no-untyped-def]
    """A sync rate at or below the measured ceiling is allowed (no over-block)."""
    deploy = DeployRequest(target_id="jetson_orin", mode="sync", fps=4.0)
    cell = matrix.evaluate(_UNIMANUAL_24, "groot", deploy)
    assert cell.allowed


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
