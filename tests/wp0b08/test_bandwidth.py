"""Acceptance ④ — bandwidth formula and the FR-CAM-011 block verdict.

The formula check is the strongest form available without hardware: it reproduces
`06` §2.9's own four worked figures (147.5 / 295 / 663 / 3539 Mbps). The block check
drives the D415×4 examples the spec pairs with a pass/fail — 3539 → blocked, 882 →
allowed — against an explicit cap, so the comparison logic is what is verified, not a
nailed threshold (`02a` WP-0B-08 ⑨).
"""

from __future__ import annotations

import pytest

from backend.camera import fixtures
from backend.camera.bandwidth import (
    descriptor_bandwidth_mbps,
    evaluate_bandwidth,
    profile_bandwidth_mbps,
    total_bandwidth_mbps,
)

_SPEC_CAP_MBPS = 3200.0


def test_formula_matches_spec_yuyv_figure() -> None:
    """640×480 YUYV @30 = 147.5 Mbps (`06` §2.9)."""
    assert profile_bandwidth_mbps(fixtures.YUYV_640_480_30) == pytest.approx(147.5, abs=0.5)


def test_formula_matches_spec_realsense_rgbd_figure() -> None:
    """RealSense color + depth 640×480@30 = 295 Mbps — depth counts as a second stream."""
    assert descriptor_bandwidth_mbps(fixtures.realsense_rgbd()) == pytest.approx(295.0, abs=0.5)


def test_formula_matches_spec_rgb888_figure() -> None:
    """1280×720 RGB888 @30 = 663 Mbps — the "> 660 Mbps" figure needs Bpp=3, not 2."""
    assert descriptor_bandwidth_mbps(fixtures.webcam_720p()) == pytest.approx(663.0, abs=1.0)


def test_depth_doubles_via_two_profiles() -> None:
    """A depth-on RealSense costs color + depth summed, not a single stream."""
    descriptor = fixtures.realsense_rgbd()
    per_profile = [profile_bandwidth_mbps(p) for p in descriptor.profiles]
    assert descriptor_bandwidth_mbps(descriptor) == pytest.approx(sum(per_profile))
    assert len(per_profile) == 2


def test_quad_full_res_blocks_at_cap() -> None:
    """D415×4 at 1280×720 color+depth = ~3539 Mbps → save/start blocked (FR-CAM-011)."""
    quad = fixtures.d415_quad_full_res()
    assert total_bandwidth_mbps(quad) == pytest.approx(3539.0, abs=1.0)
    verdict = evaluate_bandwidth(quad, _SPEC_CAP_MBPS)
    assert verdict.blocked
    assert verdict.reasons


def test_quad_reduced_res_allowed_at_cap() -> None:
    """D415×4 at 640×360 color+depth = ~882 Mbps → allowed at the same cap."""
    quad = fixtures.d415_quad_reduced()
    assert total_bandwidth_mbps(quad) == pytest.approx(882.0, abs=3.0)
    verdict = evaluate_bandwidth(quad, _SPEC_CAP_MBPS)
    assert not verdict.blocked
    assert verdict.reasons == ()


def test_per_controller_sum_blocks_even_when_total_is_split() -> None:
    """A controller whose own sum exceeds the cap blocks, per NFR-CAM-004 ②."""
    quad = fixtures.d415_quad_full_res()  # all four share usb-controller-0
    verdict = evaluate_bandwidth(quad, _SPEC_CAP_MBPS)
    assert verdict.per_controller_mbps["usb-controller-0"] == pytest.approx(3539.0, abs=1.0)
    assert any("controller" in reason for reason in verdict.reasons)
