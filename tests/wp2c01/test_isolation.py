"""WP-2C-01: the isolation surface reports which joint a residual flags, against caller thresholds.

The per-joint thresholds are WP-2C-03's calibrated output, so they are an argument here, never a
baked default. These tests check the flag/dominant reporting, the threshold boundary, and the
width refusals.
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.gmo import isolate_joints
from backend.gmo.errors import GmoJointCountError


def test_flags_joints_at_or_above_threshold() -> None:
    """Only joints whose absolute residual reaches their threshold are flagged."""
    residual = [0.1, -3.0, 0.2, 2.9, 0.0, -0.5, 0.05]
    thresholds = [1.0, 1.0, 1.0, 3.0, 1.0, 1.0, 1.0]
    isolation = isolate_joints(residual, thresholds)
    assert isolation.flagged == (1,)
    assert isolation.dominant == 1
    assert isolation.is_contact


def test_threshold_boundary_is_inclusive() -> None:
    """A residual exactly at threshold counts as flagged."""
    residual = [0.0, 0.0, 2.0, 0.0, 0.0, 0.0, 0.0]
    thresholds = [1.0, 1.0, 2.0, 1.0, 1.0, 1.0, 1.0]
    assert isolate_joints(residual, thresholds).flagged == (2,)


def test_dominant_joint_is_largest_magnitude() -> None:
    """The dominant joint is the largest absolute residual even when several are flagged."""
    residual = [4.0, -5.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    isolation = isolate_joints(residual, thresholds=[1.0] * 7)
    assert set(isolation.flagged) == {0, 1}
    assert isolation.dominant == 1


def test_all_zero_residual_is_no_contact() -> None:
    """A zero residual flags nothing and has no dominant joint."""
    isolation = isolate_joints([0.0] * 7, thresholds=[0.5] * 7)
    assert isolation.flagged == ()
    assert isolation.dominant is None
    assert not isolation.is_contact


def test_wrong_width_residual_is_refused() -> None:
    """A residual vector that is not seven wide is refused."""
    with pytest.raises(GmoJointCountError):
        isolate_joints([0.0] * 6, thresholds=[1.0] * 7)


def test_wrong_width_thresholds_are_refused() -> None:
    """A threshold vector that is not seven wide is refused."""
    with pytest.raises(GmoJointCountError):
        isolate_joints([0.0] * 7, thresholds=[1.0] * 8)


def test_negative_and_positive_residuals_use_magnitude() -> None:
    """A large negative residual flags exactly as a large positive one does."""
    negative = isolate_joints([-4.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], thresholds=[1.0] * 7)
    positive = isolate_joints([4.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], thresholds=[1.0] * 7)
    assert negative.flagged == positive.flagged == (0,)
    assert np.isclose(abs(negative.residual[0]), abs(positive.residual[0]))
