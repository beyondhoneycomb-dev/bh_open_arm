"""Joint4 same-sign guard, proven against the pinned per-side limits (FR-MAN-046).

The negative branch is: flipping joint4's sign yields a wrong symmetric point
(FAIL_BLOCKING). Rather than assert the sign vector back to itself, this cross-checks it
against LeRobot's pinned per-side joint limits (reused ``sim.ik``): for every arm joint,
the mirror sign must carry the right limit onto the left limit. joint4's limits are
identical on both sides, so only the same sign matches — a flipped joint4 would demand a
reflected left limit that does not exist, and the check fails.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("lerobot")

from backend.mirror.constants import ARM_MIRROR_SIGNS, JOINT4_INDEX
from backend.mirror.verify import (
    _mirror_interval,
    convention_matches_pinned_limits,
)


def test_every_arm_joint_sign_agrees_with_pinned_limits() -> None:
    agreements = convention_matches_pinned_limits()
    assert len(agreements) == 7
    assert all(a.matches for a in agreements)


def test_joint4_is_same_sign() -> None:
    assert ARM_MIRROR_SIGNS[JOINT4_INDEX] == 1.0
    joint4 = convention_matches_pinned_limits()[JOINT4_INDEX]
    # Same-sign means the pinned right and left intervals for joint4 are identical.
    assert joint4.right_interval == pytest.approx(joint4.left_interval)
    assert joint4.matches


def test_flipping_joint4_breaks_limit_agreement() -> None:
    # Simulate the FAIL_BLOCKING mistake: mirror joint4 with -1 and confront the pinned
    # limits. The reflected right interval no longer equals the left interval.
    joint4 = convention_matches_pinned_limits()[JOINT4_INDEX]
    flipped = _mirror_interval(joint4.right_interval, -1.0)
    assert not (
        np.isclose(flipped[0], joint4.left_interval[0])
        and np.isclose(flipped[1], joint4.left_interval[1])
    )
