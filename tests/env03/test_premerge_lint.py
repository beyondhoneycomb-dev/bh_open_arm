"""WP-ENV-03 acceptance ③ ④ — push_to_hub and plugin-naming violation fixtures fail."""

from __future__ import annotations

import premerge_lint


def test_push_to_hub_true_without_opt_in_is_rejected() -> None:
    result = premerge_lint.check_push_to_hub({"push_to_hub": True})
    assert not result.ok


def test_push_to_hub_true_with_audited_opt_in_is_allowed() -> None:
    result = premerge_lint.check_push_to_hub(
        {"push_to_hub": True, "push_to_hub_opt_in_audited": True}
    )
    assert result.ok


def test_push_to_hub_default_false_is_allowed() -> None:
    assert premerge_lint.check_push_to_hub({}).ok


def test_reserved_plugin_prefixes_are_allowed() -> None:
    for name in ("lerobot_robot_openarm", "lerobot_teleoperator_quest", "lerobot_camera_realsense"):
        assert premerge_lint.check_plugin_name(name).ok


def test_off_convention_plugin_name_is_rejected() -> None:
    for name in ("openarm_follower", "lerobot_plugin_openarm", "robot_openarm"):
        assert not premerge_lint.check_plugin_name(name).ok
