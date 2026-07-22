"""`apply_jump_guard` / `_apply_step_cap`: the per-step position-delta cap.

The jump guard clips-and-proceeds (never rejects), caps each joint against its own
`step_delta_limit_rad`, and is symmetric in both directions. It differences against
the last shaped command, so successive jogs are bounded step to step.
"""

from __future__ import annotations

import math

import pytest

from backend.jogclamp import JogClampPath
from contracts.units import Deg
from tests.wp2a03.conftest import STEP_DELTA_LIMIT_RAD


def _cap_deg(joint: int) -> float:
    """The per-joint jump cap expressed in degrees, for readable assertions."""
    return math.degrees(STEP_DELTA_LIMIT_RAD[joint])


def test_positive_jump_is_capped(seeded_path: JogClampPath) -> None:
    """A forward jump beyond the cap is clipped to the seed plus the cap."""
    capped, hit = seeded_path.apply_jump_guard((Deg(50.0), Deg(0.0), Deg(0.0)))
    assert hit
    assert capped[0].value == pytest.approx(_cap_deg(0))


def test_negative_jump_is_capped_symmetrically(seeded_path: JogClampPath) -> None:
    """A backward jump beyond the cap is clipped by the same magnitude, opposite sign."""
    capped, hit = seeded_path.apply_jump_guard((Deg(-50.0), Deg(0.0), Deg(0.0)))
    assert hit
    assert capped[0].value == pytest.approx(-_cap_deg(0))


def test_jump_within_cap_passes_unaltered(seeded_path: JogClampPath) -> None:
    """A jump inside the cap is admitted exactly — the guard is clip-and-proceed."""
    inside = _cap_deg(0) * 0.5
    capped, hit = seeded_path.apply_jump_guard((Deg(inside), Deg(0.0), Deg(0.0)))
    assert not hit
    assert capped[0].value == pytest.approx(inside)


def test_cap_is_per_joint(seeded_path: JogClampPath) -> None:
    """Each joint caps against its own limit, not a shared scalar."""
    # Joint 0 cap ≈ 5.73°, joint 1 cap ≈ 11.46°: a 9° jump caps joint 0 but not joint 1.
    capped, hit = seeded_path.apply_jump_guard((Deg(9.0), Deg(9.0), Deg(0.0)))
    assert hit
    assert capped[0].value == pytest.approx(_cap_deg(0))
    assert capped[1].value == pytest.approx(9.0)


def test_jump_guard_never_rejects(seeded_path: JogClampPath) -> None:
    """However large the jump, the guard returns a value — it clips, never stops."""
    capped, hit = seeded_path.apply_jump_guard((Deg(1e6), Deg(1e6), Deg(1e6)))
    assert hit
    assert all(math.isfinite(angle.value) for angle in capped)


def test_successive_jumps_bound_step_to_step(seeded_path: JogClampPath) -> None:
    """The reference advances each send, so a ramp is capped one step at a time."""
    first = seeded_path.apply((Deg(90.0), Deg(0.0), Deg(0.0)))
    second = seeded_path.apply((Deg(90.0), Deg(0.0), Deg(0.0)))
    # Each send advances joint 0 by at most one cap from the previous shaped command.
    assert first.accepted_deg[0].value == pytest.approx(_cap_deg(0))
    assert second.accepted_deg[0].value == pytest.approx(2 * _cap_deg(0))
