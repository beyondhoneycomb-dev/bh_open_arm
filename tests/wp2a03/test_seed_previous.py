"""Acceptance ④: `_previous_q_deg` is seeded at connect so the first send is protected.

A None-initialised jump reference skips the guard on the first send. The jog path
refuses that: an apply before `seed_previous` is rejected fail-closed, and once seeded
from the present pose the first send's jump is bounded against that real pose.
"""

from __future__ import annotations

import pytest

from backend.actuation.safety import SafetyLimits
from backend.jogclamp import JogClampNotSeededError, JogClampPath
from contracts.units import Deg


def test_apply_before_seed_is_refused(limits: SafetyLimits) -> None:
    """Shaping a target before seeding raises rather than passing an unguarded jump."""
    path = JogClampPath(limits)
    assert not path.seeded
    with pytest.raises(JogClampNotSeededError):
        path.apply((Deg(0.0), Deg(0.0), Deg(0.0)))


def test_jump_guard_before_seed_is_refused(limits: SafetyLimits) -> None:
    """The jump guard itself refuses to run without a reference, even called directly."""
    path = JogClampPath(limits)
    with pytest.raises(JogClampNotSeededError):
        path.apply_jump_guard((Deg(0.0), Deg(0.0), Deg(0.0)))


def test_first_send_is_bounded_against_the_seeded_pose(limits: SafetyLimits) -> None:
    """Seeding from present pose bounds the very first send's jump against that pose."""
    path = JogClampPath(limits)
    # Present pose sits near joint 1's operational edge; the first jog target jumps
    # further, and the guard caps it relative to the seed — not from zero, and not
    # skipped.
    path.seed_previous((Deg(0.0), Deg(40.0), Deg(0.0)))
    result = path.apply((Deg(0.0), Deg(44.0), Deg(0.0)))
    # Joint 1 jump cap is 0.2 rad ≈ 11.459°; the 4° request from the seeded 40° is
    # inside the cap, so it passes — proving the first send was measured against 40°,
    # not against an absent or zero reference.
    assert result.accepted_deg[1].value == pytest.approx(44.0)


def test_first_send_jump_is_capped_from_the_seed(limits: SafetyLimits) -> None:
    """A first-send jump beyond the cap is clipped relative to the seeded pose."""
    path = JogClampPath(limits)
    path.seed_previous((Deg(0.0), Deg(0.0), Deg(0.0)))
    result = path.apply((Deg(50.0), Deg(0.0), Deg(0.0)))
    # Joint 0 jump cap is 0.1 rad ≈ 5.7296°; the first send is capped to that from the
    # seeded 0°, so the first command is protected, not waved through.
    assert result.accepted_deg[0].value == pytest.approx(5.729577951)


def test_seed_width_must_match_envelope(limits: SafetyLimits) -> None:
    """A present pose of the wrong width is refused — the seed cannot be malformed."""
    path = JogClampPath(limits)
    with pytest.raises(ValueError, match="width"):
        path.seed_previous((Deg(0.0), Deg(0.0)))


def test_previous_advances_to_the_shaped_command(seeded_path: JogClampPath) -> None:
    """After a send the reference is the shaped command, so the next jump is relative."""
    seeded_path.apply((Deg(3.0), Deg(0.0), Deg(0.0)))
    previous = seeded_path.previous_q_deg
    assert previous is not None
    # 3° is inside joint 0's 5.73° cap, so it passes unaltered and becomes the new ref.
    assert previous[0].value == pytest.approx(3.0)
