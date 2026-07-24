"""Threshold discipline (SPINE §2-6) — the four thresholds are parameters, not pinned values.

`02c` §1.8 임계값 규율: the plan deliberately does not pin `clip_ratio_max`,
`clip_window`, `runaway_ticks`, or `starvation_ratio_max`; they derive from a nominal
rollout's normal distribution that does not exist until 4C. So the type must refuse to
invent a default — every field is required — and the only pre-4C source of values is the
clearly-labelled metering placeholder factory.
"""

from __future__ import annotations

import dataclasses

import pytest

from backend.inference.runaway import RunawayThresholds, metering_placeholder_thresholds


def test_no_threshold_has_a_default() -> None:
    """Every threshold field is required; none carries a pinned default value (SPINE §2-6)."""
    for field in dataclasses.fields(RunawayThresholds):
        assert field.default is dataclasses.MISSING, field.name
        assert field.default_factory is dataclasses.MISSING, field.name


def test_constructing_without_values_is_refused() -> None:
    """A caller cannot fall through to an unvalidated default — there is none."""
    with pytest.raises(TypeError):
        RunawayThresholds()  # type: ignore[call-arg]


def test_placeholder_factory_supplies_labelled_metering_values() -> None:
    """The metering placeholder factory returns usable-but-unvalidated thresholds."""
    thresholds = metering_placeholder_thresholds()
    assert isinstance(thresholds, RunawayThresholds)
    assert 0.0 < thresholds.clip_ratio_max <= 1.0
    assert thresholds.clip_window >= 1
    assert thresholds.delta_q_max > 0.0
    assert thresholds.runaway_ticks >= 1
    assert thresholds.ee_velocity_max > 0.0
    assert 0.0 < thresholds.starvation_ratio_max <= 1.0
