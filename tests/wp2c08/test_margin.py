"""Acceptance ⑤: the collision margin defaults to >=0.02 m and a zero must be confirmed.

The policy itself is `WP-1-06`'s; these tests prove the preflight is wired to that one
policy rather than carrying a second margin rule.
"""

from __future__ import annotations

import pytest

from backend.collision_preflight.preflight import run_preflight
from backend.safety_bringup.collision import (
    MarginConfirmationRequiredError,
    resolve_collision_margin,
)
from backend.safety_bringup.constants import COLLISION_MARGIN_DEFAULT_M


def test_default_margin_is_at_least_two_centimetres() -> None:
    resolution = resolve_collision_margin(None, False)
    assert resolution.margin_m >= 0.02
    assert resolution.margin_m == COLLISION_MARGIN_DEFAULT_M


def test_zero_margin_without_confirmation_is_refused() -> None:
    with pytest.raises(MarginConfirmationRequiredError):
        resolve_collision_margin(0.0, False)


def test_zero_margin_with_confirmation_warns() -> None:
    resolution = resolve_collision_margin(0.0, True)
    assert resolution.margin_m == 0.0
    assert resolution.warning


def test_preflight_zero_margin_without_confirmation_is_refused() -> None:
    # The preflight enforces the margin policy at the top of the run.
    with pytest.raises(MarginConfirmationRequiredError):
        run_preflight(([0.0] * 18,), requested_margin_m=0.0, confirmed_zero_margin=False)


def test_preflight_below_default_margin_carries_a_warning() -> None:
    result = run_preflight(([0.0] * 18,), requested_margin_m=0.01)
    assert result.margin.margin_m == 0.01
    assert result.margin.warning
