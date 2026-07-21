"""Acceptance ① — an N-point EE-residual distribution and its histogram.

The harness rounds ``q -> FK -> p -> IK -> q'`` over N configurations and yields the
residual distribution plus a histogram. It fixes no threshold (acceptance ⑥); these
tests check the distribution and histogram exist and are honest, not that any
residual clears a bar.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("mujoco")
pytest.importorskip("mink")
pytest.importorskip("lerobot")

from openarm_control.kinematics import IKParams

from sim.fkik import roundtrip

_FAST = IKParams(max_iters=5, dt=0.1, damping=0.1, posture_cost=0.01, lm_damping=0.01)
_SAMPLES = 16


def test_distribution_has_n_points() -> None:
    report = roundtrip.run_distribution(samples=_SAMPLES, seed=0, ik_params=_FAST)
    solved = report.solved_count()
    assert solved > 0
    residuals = report.all_residuals_m()
    # Two arms per solved sample, all finite and non-negative.
    assert residuals.size == 2 * solved
    assert bool((residuals >= 0.0).all())
    assert bool(np.isfinite(residuals).all())


def test_percentiles_are_reported() -> None:
    report = roundtrip.run_distribution(samples=_SAMPLES, seed=1, ik_params=_FAST)
    percentiles = report.percentiles()
    for key in ("p50", "p90", "p99", "max", "mean"):
        assert percentiles[key] is not None
        assert percentiles[key] >= 0.0


def test_histogram_is_rendered() -> None:
    report = roundtrip.run_distribution(samples=_SAMPLES, seed=2, ik_params=_FAST)
    histogram = report.histogram()
    assert "\n" in histogram
    assert "#" in histogram


def test_fallback_provenance_is_disclosed_not_hidden() -> None:
    # In this environment the constrained daqp QP is infeasible, so residuals come
    # through the fallback. That must be recorded, never silently absorbed.
    report = roundtrip.run_distribution(samples=_SAMPLES, seed=3, ik_params=_FAST)
    if report.fallback_firings() > 0:
        assert "fallback" in report.note
        assert "daqp" in report.note


def test_constrained_only_never_fires_the_fallback() -> None:
    # With the safety default (fallback disabled) the fallback must never fire, and a
    # run that solves nothing must say so honestly rather than fake a solution.
    report = roundtrip.run_distribution(
        samples=8, seed=4, ik_params=_FAST, allow_unconstrained_fallback=False
    )
    assert report.fallback_firings() == 0
    if report.solved_count() == 0:
        assert "no solution" in report.note
