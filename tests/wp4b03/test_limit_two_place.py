"""CG-4B-03d/e — the v2 URDF limit loader: two-place consistency and build order.

CG-4B-03d (FR-INF-036): j2 loads from `joint_limits.yaml` as -10 deg / +190 deg into
the follower config (degrees), and the IK MJCF `jnt_range` for the same joint carries
the identical value (radians). One canon, read once, written to both places.

CG-4B-03e (FR-SIM-080): the `jnt_range` override lands BEFORE `Kinematics(...)`. The
committed `OrderedIkBuild` enforces this; a build that asks for `Kinematics` before the
override is rejected, so mink can never snapshot the un-overridden ranges.
"""

from __future__ import annotations

import mujoco
import pytest
from openarm_control.config import ArmSetup
from openarm_control.kinematics import IKParams

from backend.inference.load_preflight import (
    apply_to_follower_config,
    build_canonical_ik_adapter,
    config_joint_limits_deg,
    load_canonical_limits,
    verify_two_place_consistency,
)
from sim.ik.asset import (
    EE_FRAME_TYPE,
    HOME_KEYFRAME,
    LEFT_EE_SITE,
    RIGHT_EE_SITE,
    fixed_cell_xml,
)
from sim.ik.override import IkOrderError, OrderedIkBuild

_TOL = 1e-6


def _jnt_range_rad(model: mujoco.MjModel, joint: str) -> tuple[float, float]:
    """Read a joint's `jnt_range` (radians) from a model."""
    jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, joint)
    return float(model.jnt_range[jid][0]), float(model.jnt_range[jid][1])


def test_j2_loads_as_minus10_plus190_in_both_places() -> None:
    """CG-4B-03d: j2 is -10/+190 deg in the config AND the MJCF jnt_range matches."""
    canonical = load_canonical_limits()

    # Place (a): the config-degrees value.
    config_deg = config_joint_limits_deg(canonical, "right")["joint_2"]
    assert config_deg[0] == pytest.approx(-10.0, abs=_TOL)
    assert config_deg[1] == pytest.approx(190.0, abs=_TOL)

    # Place (b): the MJCF jnt_range (radians), injected via the committed builder.
    build = build_canonical_ik_adapter(canonical)
    mjcf_rad = _jnt_range_rad(build.setup.model, "openarm_right_joint2")
    assert mjcf_rad[0] == pytest.approx(-0.17453292519943295, abs=_TOL)
    assert mjcf_rad[1] == pytest.approx(3.3161255787892263, abs=_TOL)

    # The two places agree for every joint on the side.
    report = verify_two_place_consistency(canonical, build.setup.model, "right")
    assert report.ok, report.mismatches


def test_two_place_consistency_both_sides() -> None:
    """Every joint's config-degrees equals its MJCF-radians on both arms."""
    canonical = load_canonical_limits()
    build = build_canonical_ik_adapter(canonical)

    for side in ("right", "left"):
        report = verify_two_place_consistency(canonical, build.setup.model, side)
        assert report.ok, (side, report.mismatches)


def test_canon_differs_from_lerobot_soft_limits() -> None:
    """The injected canon is the v2 URDF value, not the LeRobot soft default.

    The committed `sim.ik.build_ik_adapter` overrides j2 (right) to the soft (-9, +90);
    this loader overrides it to the canon (-10, +190), so the two must differ — proving
    the loader injects the canon rather than re-using the soft limits.
    """
    canonical = load_canonical_limits()
    build = build_canonical_ik_adapter(canonical)
    canon_rad = _jnt_range_rad(build.setup.model, "openarm_right_joint2")

    from lerobot.robots.openarm_follower.config_openarm_follower import (
        RIGHT_DEFAULT_JOINTS_LIMITS,
    )

    soft_deg = RIGHT_DEFAULT_JOINTS_LIMITS["joint_2"]
    assert soft_deg == (-9.0, 90.0)
    # Canon upper (190 deg) is well past the soft upper (90 deg).
    assert canon_rad[1] > 3.0


def test_config_injection_overwrites_side_default() -> None:
    """`apply_to_follower_config` replaces a follower config's joint_limits with the canon."""
    from lerobot.robots.openarm_follower.config_openarm_follower import OpenArmFollowerConfig

    canonical = load_canonical_limits()
    config = OpenArmFollowerConfig(port="can0", side="right")
    # Before: the +/-5 degree lock default.
    assert config.joint_limits["joint_2"] == (-5.0, 5.0)

    apply_to_follower_config(canonical, config, "right")

    assert config.joint_limits["joint_2"][0] == pytest.approx(-10.0, abs=_TOL)
    assert config.joint_limits["joint_2"][1] == pytest.approx(190.0, abs=_TOL)


def test_override_runs_before_kinematics() -> None:
    """CG-4B-03e: asking for Kinematics before the override is rejected (order contract)."""
    setup = ArmSetup.from_args(
        xml=str(fixed_cell_xml()),
        mode="bimanual",
        frame_right=RIGHT_EE_SITE,
        frame_type_right=EE_FRAME_TYPE,
        frame_left=LEFT_EE_SITE,
        frame_type_left=EE_FRAME_TYPE,
        keyframe=HOME_KEYFRAME,
    )
    build = OrderedIkBuild(setup)

    with pytest.raises(IkOrderError):
        build.build_kinematics(IKParams())


def test_loader_build_produces_canon_ranges() -> None:
    """The loader's build succeeds and the MJCF carries the canon.

    A successful build whose jnt_range equals the canon is only possible if the
    override ran before `Kinematics`; the override-after-build path would have raised.
    """
    canonical = load_canonical_limits()
    build = build_canonical_ik_adapter(canonical)

    # j6 is the narrow +/-45 deg canon on both sides; finger is mirrored.
    assert _jnt_range_rad(build.setup.model, "openarm_right_joint6") == pytest.approx(
        (-0.7853981633974483, 0.7853981633974483), abs=_TOL
    )
    assert _jnt_range_rad(build.setup.model, "openarm_left_finger_joint1") == pytest.approx(
        (0.0, 0.7853981633974483), abs=_TOL
    )
