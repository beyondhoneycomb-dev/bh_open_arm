"""Acceptance ③: a clamp is a counter, not a silent `logger.debug` clip.

LeRobot clips a `max_relative_target` overflow and logs it at debug, so a consumer
never learns the command was altered. The jog path exposes every clamp as a
per-reason tally: a caller can read how many times each stage fired and see that the
accepted target differs from the request, so saturation is observable.
"""

from __future__ import annotations

from backend.jogclamp import JogClampPath, JogClampReason
from contracts.units import Deg


def test_counter_starts_at_zero_for_every_reason(seeded_path: JogClampPath) -> None:
    """A fresh path reports zero for each reason, never a missing key."""
    counter = seeded_path.counter
    assert counter.total == 0
    for reason in JogClampReason:
        assert counter.count(reason) == 0
    assert counter.as_dict() == {
        "mechanical_limit": 0,
        "operational_limit": 0,
        "step_cap": 0,
    }


def test_operational_clamp_increments_only_its_reason(seeded_path: JogClampPath) -> None:
    """A target inside mechanical but outside operational raises no mechanical clamp."""
    # Joint 1: 46° is inside the mechanical [-90, 90] but outside the operational
    # [-45, 45], so the operational stage clamps and the mechanical stage does not.
    result = seeded_path.apply((Deg(0.0), Deg(46.0), Deg(0.0)))
    assert JogClampReason.OPERATIONAL_LIMIT in result.reasons
    assert JogClampReason.MECHANICAL_LIMIT not in result.reasons
    assert seeded_path.counter.count(JogClampReason.OPERATIONAL_LIMIT) == 1
    assert seeded_path.counter.count(JogClampReason.MECHANICAL_LIMIT) == 0


def test_clamp_makes_accepted_differ_from_request(seeded_path: JogClampPath) -> None:
    """The accepted target differs from the request when a clamp fired — never hidden."""
    request = (Deg(0.0), Deg(60.0), Deg(0.0))
    result = seeded_path.apply(request)
    assert result.clamped
    assert result.accepted_deg[1].value != request[1].value


def test_unclamped_request_records_nothing(seeded_path: JogClampPath) -> None:
    """A request inside every bound and within the jump cap increments no counter."""
    # Joint 1 jump cap 0.2 rad ≈ 11.46°; 5° is inside it and inside every position bound.
    result = seeded_path.apply((Deg(0.0), Deg(5.0), Deg(0.0)))
    assert not result.clamped
    assert seeded_path.counter.total == 0


def test_repeated_clamps_accumulate(seeded_path: JogClampPath) -> None:
    """Each shaped command that clamps adds to the running tally."""
    for _ in range(3):
        seeded_path.apply((Deg(0.0), Deg(89.0), Deg(0.0)))
    # Each call clamps joint 1 to operational 45° and caps the jump; the operational
    # tally therefore rises once per call.
    assert seeded_path.counter.count(JogClampReason.OPERATIONAL_LIMIT) == 3
