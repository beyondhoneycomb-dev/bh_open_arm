"""WP-3B-14 acceptance ① — the KER performs no IK (static and behavioural).

The KER reads joint angles, so `get_action()` must return them directly as `.pos`
degrees, unchanged by any inverse-kinematics solve or coordinate transform. An IK call
is the defect (FR-TEL-064), so this proves it two ways: behaviourally, the action is a
deterministic identity of the joints read; statically, no IK import or solver call
appears in the package.
"""

from __future__ import annotations

from pathlib import Path

from backend.teleop.ker import (
    RULE_IK,
    MockKerDevice,
    OpenArmKER,
    OpenArmKERConfig,
    check_package,
    check_source,
)
from contracts.teleop import (
    KER_PERFORMS_IK,
    TeleopValidity,
    is_action_dim_position_only,
    reserved_ker_slot,
)

_KER_PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "backend" / "teleop" / "ker"

_BIMANUAL_ANGLES = tuple(float(value) for value in range(10, 26))
_SINGLE_ANGLES = tuple(float(value) for value in range(3, 11))


def _connected_ker(config: OpenArmKERConfig, angles: tuple[float, ...]) -> OpenArmKER:
    """Build a KER driven by a mock reading fixed joint angles."""
    teleop = OpenArmKER(config)
    teleop.device = MockKerDevice.constant(angles, TeleopValidity.OK)
    teleop.connect()
    return teleop


def test_get_action_is_the_joint_angles_unchanged() -> None:
    """Every `.pos` value equals the joint angle read — no IK, no transform."""
    teleop = _connected_ker(OpenArmKERConfig(bimanual=True), _BIMANUAL_ANGLES)
    action = teleop.get_action()
    positions = [value for key, value in action.items() if key.endswith(".pos")]
    assert tuple(positions) == _BIMANUAL_ANGLES
    assert is_action_dim_position_only(action)


def test_single_arm_get_action_is_also_identity() -> None:
    """The single-arm keyset maps its 8 joint angles straight through as well."""
    teleop = _connected_ker(OpenArmKERConfig(bimanual=False), _SINGLE_ANGLES)
    action = teleop.get_action()
    positions = [value for key, value in action.items() if key.endswith(".pos")]
    assert tuple(positions) == _SINGLE_ANGLES


def test_action_is_deterministic_across_reads() -> None:
    """The same joint frame yields the same action every read (no integrating IK state)."""
    teleop = _connected_ker(OpenArmKERConfig(bimanual=True), _BIMANUAL_ANGLES)
    assert teleop.get_action() == teleop.get_action() == teleop.get_action()


def test_package_source_has_no_inverse_kinematics() -> None:
    """No IK import or solver call appears anywhere in the KER package (static half)."""
    ik_violations = [v for v in check_package(_KER_PACKAGE_ROOT) if v.rule == RULE_IK]
    assert ik_violations == []


def test_ik_import_ban_is_not_vacuous() -> None:
    """Importing a kinematics library trips the IK ban."""
    for source in ("import openarm_control\n", "import mink\n", "from a.kinematics import solve\n"):
        assert any(v.rule == RULE_IK for v in check_source(source))


def test_ik_solver_call_ban_is_not_vacuous() -> None:
    """Calling an IK solver trips the IK ban."""
    for source in ("y = solve_ik(x)\n", "cfg.set_target(t)\n", "kin.integrate_inplace(dt)\n"):
        assert any(v.rule == RULE_IK for v in check_source(source))


def test_contract_pins_the_slot_to_perform_no_ik() -> None:
    """The frozen reserved slot the KER fills performs no IK (FR-TEL-064)."""
    assert KER_PERFORMS_IK is False
    assert reserved_ker_slot().performs_ik is False
