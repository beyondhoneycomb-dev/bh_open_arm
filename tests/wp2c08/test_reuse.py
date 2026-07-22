"""No second source of truth: WP-2C-08 reuses WP-1-06 and targets.matrix by identity.

The task forbids a second link7 checker, a second margin policy, or a re-typed target list.
These identity checks prove reuse rather than reimplementation — the same function objects
and the same tuple, not lookalikes.
"""

from __future__ import annotations

from backend.collision_preflight import constants, link7, preflight
from backend.safety_bringup import collision as safety_collision
from targets.matrix import FLEET_TARGETS


def test_link7_check_is_the_safety_bringup_function() -> None:
    assert link7.assert_link7_collision_in_mjcf is safety_collision.assert_link7_collision_in_mjcf
    assert link7.assert_link7_collision_in_urdf is safety_collision.assert_link7_collision_in_urdf
    assert link7.inject_link7_collision_urdf is safety_collision.inject_link7_collision_urdf


def test_margin_policy_is_the_safety_bringup_policy() -> None:
    assert preflight.resolve_collision_margin is safety_collision.resolve_collision_margin


def test_mjcf_locator_is_the_safety_bringup_locator() -> None:
    # The committed asset is located through the WP-0C-03 owning package, one path canon.
    from backend.collision_preflight import model

    assert model.committed_mjcf_path is safety_collision.committed_mjcf_path


def test_bench_targets_are_the_fleet_targets() -> None:
    assert constants.BENCH_TARGETS is FLEET_TARGETS
