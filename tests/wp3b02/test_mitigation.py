"""RUNS-HERE ④ — the five mitigation steps and the dual frame-timeout diagnosis.

The ladder is offered whenever a configuration is blocked, in a fixed cheapest-first
order, and the RealSense frame-timeout symptom is diagnosed against both bandwidth
and power rather than bandwidth alone.
"""

from __future__ import annotations

from backend.sensing.bandwidth.constants import (
    CAUSE_BANDWIDTH,
    CAUSE_POWER,
    FRAME_TIMEOUT_SYMPTOM,
    MITIGATION_STEP_COUNT,
)
from backend.sensing.bandwidth.mitigation import (
    diagnose_frame_timeout,
    mitigation_steps,
)


def test_exactly_five_steps_offered() -> None:
    """The ladder is five rungs (`02b` WP-3C-01 five-step ladder)."""
    steps = mitigation_steps()
    assert len(steps) == MITIGATION_STEP_COUNT == 5


def test_steps_are_ordered_cheapest_first() -> None:
    """Order is 1..5 and the sequence is format → controller → depth → fps → resolution."""
    steps = mitigation_steps()
    assert [step.order for step in steps] == [1, 2, 3, 4, 5]
    joined = [step.action.lower() for step in steps]
    assert "mjpeg" in joined[0]
    assert "controller" in joined[1]
    assert "depth" in joined[2]
    assert "frame rate" in joined[3]
    assert "resolution" in joined[4]


def test_every_step_states_a_rationale() -> None:
    """Each rung says why it lowers the budget, not just what to change."""
    assert all(step.rationale.strip() for step in mitigation_steps())


def test_frame_timeout_diagnosed_against_both_causes() -> None:
    """The symptom maps to bandwidth AND power, never one alone (`02b` WP-3B-02 ④)."""
    diagnosis = diagnose_frame_timeout()
    assert diagnosis.symptom == FRAME_TIMEOUT_SYMPTOM
    labels = {cause.label for cause in diagnosis.causes}
    assert labels == {CAUSE_BANDWIDTH, CAUSE_POWER}
    assert all(cause.check.strip() for cause in diagnosis.causes)
