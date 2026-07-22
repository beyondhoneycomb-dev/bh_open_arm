"""RUNS-HERE ②③ — the save/start block and depth counting as a second stream.

② An over-cap configuration is refused, not warned about. ③ Turning depth on adds a
second stream and can be the sole reason a passing configuration becomes blocked.
The formula behind both is imported from WP-0B-08 and reused through the block; these
tests exercise the block, not the arithmetic (which WP-0B-08 already pins to spec).
"""

from __future__ import annotations

import pytest

from backend.camera import fixtures as camera_fixtures
from backend.sensing.bandwidth.budget import (
    BandwidthBudgetError,
    enforce_budget,
    evaluate_budget,
)
from backend.sensing.bandwidth.constants import ACTION_SAVE, ACTION_START
from tests.wp3b02 import fixtures

_CAP_MBPS = 3200.0


def test_over_cap_start_is_blocked() -> None:
    """D415×4 at full res (~3539 Mbps) refuses start — a block, not a warning (②)."""
    quad = camera_fixtures.d415_quad_full_res()
    with pytest.raises(BandwidthBudgetError) as excinfo:
        enforce_budget(quad, _CAP_MBPS, action=ACTION_START)
    assert excinfo.value.action == ACTION_START
    assert excinfo.value.decision.blocked


def test_over_cap_save_is_blocked() -> None:
    """The same over-cap configuration also refuses save (both save and start blocked)."""
    quad = camera_fixtures.d415_quad_full_res()
    with pytest.raises(BandwidthBudgetError) as excinfo:
        enforce_budget(quad, _CAP_MBPS, action=ACTION_SAVE)
    assert excinfo.value.action == ACTION_SAVE


def test_within_cap_allows_and_returns_decision() -> None:
    """A reduced-res quad (~882 Mbps) is allowed and enforce returns its decision."""
    quad = camera_fixtures.d415_quad_reduced()
    decision = enforce_budget(quad, _CAP_MBPS, action=ACTION_START)
    assert not decision.blocked
    assert decision.mitigations == ()


def test_depth_toggle_flips_the_block() -> None:
    """Depth off passes, depth on blocks, at one cap — depth is a second stream (③)."""
    depth_off = fixtures.realsense_trio(depth=False)
    depth_on = fixtures.realsense_trio(depth=True)

    allowed = evaluate_budget(depth_off, fixtures.FLIP_CAP_MBPS)
    blocked = evaluate_budget(depth_on, fixtures.FLIP_CAP_MBPS)

    assert not allowed.blocked
    assert blocked.blocked
    assert allowed.verdict.total_mbps == pytest.approx(fixtures.STREAM_DEPTH_OFF_MBPS)
    assert blocked.verdict.total_mbps == pytest.approx(fixtures.STREAM_DEPTH_ON_MBPS)


def test_depth_on_doubles_the_camera_total() -> None:
    """Each RealSense's total is exactly its color plus its depth stream."""
    off = evaluate_budget(fixtures.realsense_trio(depth=False), fixtures.FLIP_CAP_MBPS)
    on = evaluate_budget(fixtures.realsense_trio(depth=True), fixtures.FLIP_CAP_MBPS)
    assert on.verdict.total_mbps == pytest.approx(2 * off.verdict.total_mbps)


def test_blocked_decision_carries_mitigations() -> None:
    """A blocked decision offers the mitigation ladder; a passing one offers none."""
    blocked = evaluate_budget(camera_fixtures.d415_quad_full_res(), _CAP_MBPS)
    assert blocked.blocked
    assert blocked.mitigations
