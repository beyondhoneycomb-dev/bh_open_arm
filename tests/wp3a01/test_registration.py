"""The five WP-3A-01 registration rules, each proven by acceptance (`02b` §5.2).

① geometry lives only in the dict (proven in test_no_redefinition), ② unspecified
width/height/fps blocks collection start, ③ the arm prefix is auto-attached and
surfaced for the UI, ④ a slot-name collision is rejected before save, ⑤ a sim
scene camera lives in a namespace that cannot collide with a real slot.
"""

from __future__ import annotations

import pytest

import contracts.camera_registry as cam
from contracts.prim import ARM_PREFIXES, SIM_NAMESPACE_PREFIX, FrameType

RGB = frozenset({FrameType.RGB})
RGBD = frozenset({FrameType.RGB, FrameType.DEPTH})


def test_capability_floor_requires_rgb() -> None:
    """A camera without the required RGB capability is refused (RGB required, depth optional)."""
    with pytest.raises(cam.CameraRegistryError, match="required capability"):
        cam.make_top_level_camera("front", frozenset({FrameType.DEPTH}))

    rgb_only = cam.make_top_level_camera("front", RGB)
    with_depth = cam.make_top_level_camera("overhead", RGBD)
    assert not rgb_only.has_depth
    assert with_depth.has_depth


def test_unspecified_geometry_blocks_collection_start() -> None:
    """② A registered but unconfigured camera blocks collection start until dims are set."""
    registry = cam.CameraRegistry()
    registry.register(cam.make_top_level_camera("front", RGB))

    assert registry.cameras["front"].is_configured is False
    with pytest.raises(cam.CameraRegistryError, match="collection start blocked"):
        registry.assert_collection_startable()


def test_configured_geometry_allows_collection_start() -> None:
    """Once every camera has width/height/fps, collection start is no longer blocked."""
    registry = cam.CameraRegistry()
    registry.register(cam.make_top_level_camera("front", RGB).configured(640, 480, 30))
    registry.assert_collection_startable()
    assert registry.unconfigured() == ()


def test_arm_prefix_is_auto_attached_and_surfaced_for_ui() -> None:
    """③ Per-arm registration attaches left_/right_ and exposes a UI note about it."""
    left = cam.make_arm_camera("left", "wrist", RGB)
    right = cam.make_arm_camera("right", "wrist", RGB)

    assert left.slot.value == f"{ARM_PREFIXES['left']}wrist"
    assert right.slot.value == f"{ARM_PREFIXES['right']}wrist"
    assert left.arm == "left"
    note = left.ui_arm_prefix_note()
    assert note is not None and "left_" in note

    top = cam.make_top_level_camera("front", RGB)
    assert top.arm is None
    assert top.ui_arm_prefix_note() is None


def test_slot_name_collision_rejected_before_save() -> None:
    """④ A duplicate slot key is refused, and the store is left with the first camera."""
    registry = cam.CameraRegistry()
    registry.register(cam.make_top_level_camera("front", RGB).configured(640, 480, 30))

    with pytest.raises(cam.CameraRegistryError, match="already registered"):
        registry.register(cam.make_top_level_camera("front", RGBD).configured(1280, 720, 15))

    assert set(registry.cameras) == {"front"}
    assert not registry.cameras["front"].has_depth


def test_sim_camera_lives_in_a_separate_namespace() -> None:
    """⑤ A sim scene camera cannot collide with a real camera of the same base name."""
    registry = cam.CameraRegistry()
    real = cam.make_top_level_camera("front", RGB).configured(640, 480, 30)
    sim = cam.make_sim_camera("front", RGB).configured(640, 480, 30)

    registry.register(real)
    registry.register(sim)  # same base name, but a different (sim_) slot: no collision

    assert real.slot.value == "front"
    assert sim.slot.value == f"{SIM_NAMESPACE_PREFIX}front"
    assert sim.is_sim and not real.is_sim
    assert {spec.slot.value for spec in registry.real_cameras()} == {"front"}
    assert {spec.slot.value for spec in registry.sim_cameras()} == {"sim_front"}


def test_sim_conformance_is_required_subset_not_exact_match() -> None:
    """Simulation conforms when it meets the required capability subset, not an exact stream set."""
    real = cam.make_top_level_camera("overhead", RGBD)
    sim = cam.make_sim_camera("overhead", RGB)
    assert cam.sim_satisfies(real, sim)
