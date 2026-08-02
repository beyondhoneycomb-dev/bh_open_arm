"""The admission gates that decide whether a person is asked to hold a live arm.

Each is checked against ground truth the runner does not own: whether the rig binding resolves
to something callable, which motor ids the fitted tool declares, and what the calibration files
on disk record. A gate that agrees with itself is what this file exists to rule out.

Every result built here carries more than one line. A one-line result cannot distinguish the
conjunction the verdict is from the disjunction a one-character edit turns it into, and the
difference is a session that schedules an engage while three of its five gates printed a refusal.
"""

from __future__ import annotations

import importlib.util
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

import backend.can.lock
import backend.can.rid.reverify
import backend.config.store
import backend.endeffector
import backend.preflight
import ops.hw.canbind
from backend.endeffector import GRIPPER_SEND_ID, gripper_build, spatula_build
from backend.preflight import PreflightInputs
from ops.hw.canbind import ArmRole, BindingError, ChannelBinding
from ops.hw.canbind.discovery import CanChannel
from scripts import torque_session as session

# A CAN adapter's udev position and per-channel index, enough to build the reboot-stable channel
# key `check_binding` matches a stored binding against.
STUB_ID_PATH = "pci-0000:00:14.0-usb-0:8:1.0"
STUB_DEV_IDS = ("0x0", "0x1")
STUB_BITRATE_BPS = 1_000_000
STUB_LINK_STATE = "ERROR-ACTIVE"


def _config(tmp_path: Path) -> session.SessionConfig:
    """A session config confined to a temporary tree."""
    return session.SessionConfig(
        arm=session.ARM_LEFT,
        captures_root=tmp_path,
        rid_capture_dir=tmp_path / "rid",
        operator="test",
        candump_path=None,
    )


def _rig_binding_exists() -> bool:
    """Whether the torque rig binding is present, probed without the runner's own helper."""
    if importlib.util.find_spec(session.TORQUE_RIG_MODULE) is None:
        return False
    module = importlib.import_module(session.TORQUE_RIG_MODULE)
    return hasattr(module, session.TORQUE_RIG_FACTORY)


def _result_of(*lines: tuple[bool, str]) -> session.AdmissionResult:
    """An admission result carrying the given `(passed, label)` lines, in order."""
    result = session.AdmissionResult()
    for passed, label in lines:
        result.record(passed, label, "detail")
    return result


def test_one_refusal_among_passes_blocks_the_session() -> None:
    """The verdict is the conjunction of every line, which needs more than one line to show."""
    result = _result_of((True, "CAN 바인딩"), (False, "토크 쓰기 경로"), (True, "장착 엔드이펙터"))
    assert result.ok is False


def test_a_refusal_on_the_first_line_blocks_the_session() -> None:
    result = _result_of((False, "CAN 바인딩"), (True, "영점 캘리브레이션"))
    assert result.ok is False


def test_a_refusal_on_the_last_line_blocks_the_session() -> None:
    result = _result_of((True, "CAN 바인딩"), (False, "영점 캘리브레이션"))
    assert result.ok is False


def test_a_result_whose_every_line_passed_admits_the_session() -> None:
    result = _result_of((True, "CAN 바인딩"), (True, "영점 캘리브레이션"))
    assert result.ok is True


def test_every_refused_line_is_marked_refused_in_what_the_operator_reads() -> None:
    rendered = _result_of((True, "통과한 것"), (False, "거부한 것")).render()
    assert rendered.count("[거부]") == 1
    assert rendered.count("[통과]") == 1


def test_torque_write_path_gate_is_installed() -> None:
    assert session._admit_torque_write_path in session.ADMISSION_GATES


def _a_writer_factory(_slots: object) -> object:
    """Stand in for the single writer's factory; the gate reads its presence, never calls it."""
    return object()


def test_torque_write_path_gate_refuses_while_the_rig_binding_is_absent(tmp_path: Path) -> None:
    if _rig_binding_exists():
        pytest.skip(f"{session.TORQUE_RIG_MODULE}.{session.TORQUE_RIG_FACTORY} now exists")
    result = session.AdmissionResult()
    session._admit_torque_write_path(result, _config(tmp_path))
    assert result.ok is False
    assert session.TORQUE_RIG_FACTORY in result.render()


def test_torque_write_path_gate_refuses_while_the_single_writer_is_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The rig binding alone is half a write path, and half a write path engages nothing.

    A gate that read the binding's presence as the path would admit a session whose every
    torque step then refuses — and the operator is holding a brakeless arm by then, because the
    timetable put the engage thirty seconds after the admission printed. So the binding is left
    present and only the writer is cleared: that is the half-assembled state the gate is for.
    """
    if not _rig_binding_exists():
        pytest.skip(f"{session.TORQUE_RIG_MODULE}.{session.TORQUE_RIG_FACTORY} does not exist yet")
    monkeypatch.setattr(session, "BIMANUAL_CAN_WRITER", None)
    result = session.AdmissionResult()
    session._admit_torque_write_path(result, _config(tmp_path))
    assert result.ok is False
    assert "단일 작성자" in result.render()


def test_torque_write_path_gate_admits_once_both_halves_exist(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    if not _rig_binding_exists():
        pytest.skip(f"{session.TORQUE_RIG_MODULE}.{session.TORQUE_RIG_FACTORY} does not exist yet")
    monkeypatch.setattr(session, "BIMANUAL_CAN_WRITER", _a_writer_factory)
    result = session.AdmissionResult()
    session._admit_torque_write_path(result, _config(tmp_path))
    assert result.ok is True


def _point_the_rig_at(
    monkeypatch: pytest.MonkeyPatch, module_name: str, attribute_name: str
) -> None:
    """Resolve the rig binding through a stand-in module with a known attribute shape.

    `json` is used because it is guaranteed to import and carries both a callable and a plain
    string at module level. What is under test is what the runner accepts as a write path, not
    anything about JSON.
    """
    monkeypatch.setattr(session, "TORQUE_RIG_MODULE", module_name)
    monkeypatch.setattr(session, "TORQUE_RIG_FACTORY", attribute_name)


def test_a_name_bound_to_a_non_callable_is_not_a_torque_write_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _point_the_rig_at(monkeypatch, "json", "__name__")
    assert session.torque_rig_factory() is None
    result = session.AdmissionResult()
    session._admit_torque_write_path(result, _config(tmp_path))
    assert result.ok is False


def test_a_missing_name_is_not_a_torque_write_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _point_the_rig_at(monkeypatch, "json", "build_engage_bus")
    assert session.torque_rig_factory() is None
    result = session.AdmissionResult()
    session._admit_torque_write_path(result, _config(tmp_path))
    assert result.ok is False


def test_a_name_bound_to_a_callable_is_a_torque_write_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _point_the_rig_at(monkeypatch, "json", "loads")
    monkeypatch.setattr(session, "BIMANUAL_CAN_WRITER", _a_writer_factory)
    assert callable(session.torque_rig_factory())
    result = session.AdmissionResult()
    session._admit_torque_write_path(result, _config(tmp_path))
    assert result.ok is True


def test_end_effector_gate_refuses_a_profile_that_polls_the_gripper_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(backend.endeffector, "default_profile", gripper_build)
    result = session.AdmissionResult()
    session._admit_end_effector(result, _config(tmp_path))
    assert result.ok is False
    assert f"{GRIPPER_SEND_ID:#04x}" in result.render()


def test_end_effector_gate_admits_the_build_with_no_motor_on_the_gripper_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(backend.endeffector, "default_profile", spatula_build)
    result = session.AdmissionResult()
    session._admit_end_effector(result, _config(tmp_path))
    assert result.ok is True


def test_this_rig_is_admitted_by_the_end_effector_gate(tmp_path: Path) -> None:
    result = session.AdmissionResult()
    session._admit_end_effector(result, _config(tmp_path))
    assert result.ok is True, result.render()


def _calibration_tree(
    tmp_path: Path, power_cycle_verified: bool, rezero_each_session: bool
) -> Path:
    """This bench's real calibration files, copied into `tmp_path` with the two flags replaced.

    Copied rather than synthesized so the vectors, the checksum and the schema generation stay
    whatever the rig actually wrote; only the flags under test differ.
    """
    from backend.calibration.atomic_io import (
        calibration_path_for,
        load_calibration,
        save_calibration_atomic,
    )
    from backend.config.store import default_config_directory

    source = default_config_directory() / session.CALIBRATION_DIRNAME
    directory = tmp_path / session.CALIBRATION_DIRNAME
    directory.mkdir(parents=True, exist_ok=True)
    for robot_id in session.CALIBRATION_ROBOT_IDS.values():
        calibration = load_calibration(calibration_path_for(source, robot_id))
        save_calibration_atomic(
            calibration_path_for(directory, robot_id),
            replace(
                calibration,
                zero_power_cycle_verified=power_cycle_verified,
                require_rezero_each_session=rezero_each_session,
            ),
        )
    return tmp_path


def _admit_calibration_from(monkeypatch: pytest.MonkeyPatch, root: Path) -> session.AdmissionResult:
    """Run the calibration gate against a config directory of our choosing."""
    monkeypatch.setattr(backend.config.store, "default_config_directory", lambda: root)
    result = session.AdmissionResult()
    session._admit_calibration(result, _config(root))
    return result


def test_this_rig_is_admitted_by_the_calibration_gate(tmp_path: Path) -> None:
    result = session.AdmissionResult()
    session._admit_calibration(result, _config(tmp_path))
    assert result.ok is True, result.render()


def test_an_unverified_power_cycle_zero_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _calibration_tree(tmp_path, power_cycle_verified=False, rezero_each_session=True)
    assert _admit_calibration_from(monkeypatch, root).ok is False


def test_turning_off_the_rezero_requirement_does_not_verify_the_power_cycle(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _calibration_tree(tmp_path, power_cycle_verified=False, rezero_each_session=False)
    assert _admit_calibration_from(monkeypatch, root).ok is False


def test_a_verified_power_cycle_zero_is_admitted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _calibration_tree(tmp_path, power_cycle_verified=True, rezero_each_session=True)
    assert _admit_calibration_from(monkeypatch, root).ok is True


def test_a_gate_that_raises_is_recorded_as_a_refusal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def _explode(_result: object, _config: object) -> None:
        raise RuntimeError("bus went away")

    monkeypatch.setattr(session, "ADMISSION_GATES", (_explode,))
    assert session.admit(_config(tmp_path)).ok is False


def _channel(dev_id: str) -> CanChannel:
    """One CAN channel of the stub adapter, as `list_can_channels` would report it."""
    return CanChannel(
        interface=f"can{STUB_DEV_IDS.index(dev_id)}",
        id_path=STUB_ID_PATH,
        dev_id=dev_id,
        driver="peak_usb",
        state=STUB_LINK_STATE,
        bitrate_bps=STUB_BITRATE_BPS,
    )


LEFT_CHANNEL = _channel(STUB_DEV_IDS[0])
RIGHT_CHANNEL = _channel(STUB_DEV_IDS[1])


def _bind_channels(monkeypatch: pytest.MonkeyPatch, present: tuple[CanChannel, ...]) -> None:
    """Bind both follower roles to the stub adapter and expose only `present` as plugged in."""
    binding = ChannelBinding(
        roles={
            ArmRole.FOLLOWER_LEFT: LEFT_CHANNEL.channel_key,
            ArmRole.FOLLOWER_RIGHT: RIGHT_CHANNEL.channel_key,
        }
    )
    monkeypatch.setattr(ops.hw.canbind, "load_binding", lambda _path: binding)
    monkeypatch.setattr(ops.hw.canbind, "list_can_channels", lambda: list(present))


def test_the_binding_gate_admits_both_follower_channels_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _bind_channels(monkeypatch, (LEFT_CHANNEL, RIGHT_CHANNEL))
    result = session.AdmissionResult()
    session._admit_binding(result, _config(tmp_path))
    assert result.ok is True, result.render()


def test_the_binding_gate_refuses_when_the_left_channel_is_gone(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _bind_channels(monkeypatch, (RIGHT_CHANNEL,))
    result = session.AdmissionResult()
    session._admit_binding(result, _config(tmp_path))
    assert result.ok is False
    assert ArmRole.FOLLOWER_LEFT.value in result.render()


def test_the_binding_gate_refuses_when_the_right_channel_is_gone(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """can1 is the right arm on this rig, confirmed by which arm moved.

    Judged separately from the left because a required set narrowed to the left role alone still
    refuses every left-arm case, and the session that would then be admitted is a right-arm
    session whose channel is not plugged in.
    """
    _bind_channels(monkeypatch, (LEFT_CHANNEL,))
    result = session.AdmissionResult()
    session._admit_binding(result, _config(tmp_path))
    assert result.ok is False
    assert ArmRole.FOLLOWER_RIGHT.value in result.render()


def test_the_binding_gate_records_a_load_failure_as_a_refusal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def _refuse(_path: Path) -> ChannelBinding:
        raise BindingError("binding file is not readable")

    monkeypatch.setattr(ops.hw.canbind, "load_binding", _refuse)
    result = session.AdmissionResult()
    session._admit_binding(result, _config(tmp_path))
    assert result.ok is False
    assert "binding file is not readable" in result.render()


def test_the_binding_gate_records_an_os_error_as_a_refusal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def _refuse(_path: Path) -> ChannelBinding:
        raise OSError("no such file")

    monkeypatch.setattr(ops.hw.canbind, "load_binding", _refuse)
    result = session.AdmissionResult()
    session._admit_binding(result, _config(tmp_path))
    assert result.ok is False


def _one_arm_unverified(tmp_path: Path, unverified_arm: str) -> Path:
    """This bench's calibration files, with the power-cycle flag cleared on one arm only."""
    from backend.calibration.atomic_io import (
        calibration_path_for,
        load_calibration,
        save_calibration_atomic,
    )
    from backend.config.store import default_config_directory

    source = default_config_directory() / session.CALIBRATION_DIRNAME
    directory = tmp_path / session.CALIBRATION_DIRNAME
    directory.mkdir(parents=True, exist_ok=True)
    for arm, robot_id in session.CALIBRATION_ROBOT_IDS.items():
        calibration = load_calibration(calibration_path_for(source, robot_id))
        save_calibration_atomic(
            calibration_path_for(directory, robot_id),
            replace(calibration, zero_power_cycle_verified=arm != unverified_arm),
        )
    return tmp_path


@pytest.mark.parametrize("unverified_arm", session.ARMS)
def test_each_arms_zero_is_required_on_its_own(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, unverified_arm: str
) -> None:
    """Both arms are polled every session, so either arm's unwatched zero blocks it.

    The gate loops over both arms. A loop shortened to the first arm still refuses every case
    where the left arm is the unverified one, and the right arm's zero then stops being required
    at all — this rig engages at an angle nobody measured on the arm nobody checked.
    """
    root = _one_arm_unverified(tmp_path, unverified_arm)
    result = _admit_calibration_from(monkeypatch, root)
    assert result.ok is False
    assert unverified_arm in result.render()


@dataclass(frozen=True)
class StubEvaluation:
    """One judged RID dump: the interface the gate filters on, and which file it came from.

    Two dumps of one channel are what the gate has to judge both of, so they have to be
    distinguishable from each other by something other than their position in a list.
    """

    iface: str
    dump: str


@dataclass(frozen=True)
class StubReport:
    """The two members `_admit_preflight` reads off a preflight report."""

    may_enable_torque: bool
    summary: str

    def blocking_summary(self) -> str:
        """Render this report the way `PreflightReport` does."""
        return self.summary


class StubLockManager:
    """Stands in for the writer-lock manager, taking no lock on any real interface."""

    def acquire_all(self, ifaces: Sequence[str]) -> None:
        """Take nothing."""

    def release_all(self) -> None:
        """Release nothing."""

    def lock_state(self, ifaces: Sequence[str]) -> tuple[object, ...]:
        """Report one opaque state per interface; only the stubbed preflight reads it."""
        return tuple(iface for iface in ifaces)


def _stub_preflight(
    monkeypatch: pytest.MonkeyPatch, judged: Sequence[tuple[StubEvaluation, StubReport]]
) -> None:
    """Point the preflight gate at prepared RID dumps, each with its own prepared verdict.

    Everything the gate reaches outside its own decision is replaced: the RID hook, the writer
    lock, the link read, and the preflight itself. What is left under test is which dumps the gate
    judges and what it records.

    Each verdict is looked up by the dump it belongs to rather than by call order, so a gate that
    judges the wrong dump gets that dump's verdict and not the one the test happened to list
    first.
    """
    verdicts: dict[object, StubReport] = dict(judged)

    class _Preflight:
        def run(self, inputs: PreflightInputs) -> StubReport:
            return verdicts[inputs.rid.evaluation]

    def _dumps(_directory: Path, **_expected: object) -> list[StubEvaluation]:
        """Hand back the prepared dumps for whatever directory the gate points at."""
        return [evaluation for evaluation, _ in judged]

    monkeypatch.setattr(backend.can.rid.reverify, "reverify_from_fixture", _dumps)
    monkeypatch.setattr(backend.can.lock, "LockManager", StubLockManager)
    monkeypatch.setattr(backend.preflight, "JogSessionPreflight", _Preflight)
    monkeypatch.setattr(
        session,
        "run_command",
        lambda _argv: subprocess.CompletedProcess(_argv, returncode=1, stdout="", stderr=""),
    )


def _preflight_verdict(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    judged: Sequence[tuple[StubEvaluation, StubReport]],
    rid_dir_exists: bool = True,
) -> session.AdmissionResult:
    """Run the preflight gate over stubbed evidence and return what it recorded."""
    _bind_channels(monkeypatch, (LEFT_CHANNEL, RIGHT_CHANNEL))
    _stub_preflight(monkeypatch, judged)
    config = _config(tmp_path)
    if rid_dir_exists:
        config.rid_capture_dir.mkdir(parents=True, exist_ok=True)
    result = session.AdmissionResult()
    session._admit_preflight(result, config)
    return result


def _selected_iface() -> str:
    """The interface a left-arm session resolves to with the stub adapter bound."""
    return LEFT_CHANNEL.interface


def _permitted() -> StubReport:
    """A report in which all five preconditions passed."""
    return StubReport(may_enable_torque=True, summary="torque-ON permitted")


def test_the_preflight_gate_refuses_a_report_that_blocks_torque_on(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The five WP-2A-09 preconditions are the verdict, not a line of text beside it."""
    blocked = StubReport(may_enable_torque=False, summary="torque-ON BLOCKED by 2 precondition(s)")
    result = _preflight_verdict(
        monkeypatch, tmp_path, [(StubEvaluation(_selected_iface(), "can0.json"), blocked)]
    )
    assert result.ok is False
    assert blocked.summary in result.render()


def test_the_preflight_gate_admits_a_report_that_permits_torque_on(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    result = _preflight_verdict(
        monkeypatch, tmp_path, [(StubEvaluation(_selected_iface(), "can0.json"), _permitted())]
    )
    assert result.ok is True, result.render()


def test_a_second_dump_of_the_same_channel_is_judged_too(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """One evaluation per capture file: a passing dump may not stand in for a failing one."""
    iface = _selected_iface()
    blocked = StubReport(may_enable_torque=False, summary="the re-dump blocks")
    result = _preflight_verdict(
        monkeypatch,
        tmp_path,
        [
            (StubEvaluation(iface, "can0-first.json"), _permitted()),
            (StubEvaluation(iface, "can0-second.json"), blocked),
        ],
    )
    assert result.ok is False
    assert blocked.summary in result.render()


def test_a_blocking_first_dump_is_not_excused_by_a_later_one(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    iface = _selected_iface()
    blocked = StubReport(may_enable_torque=False, summary="the earlier dump blocks")
    result = _preflight_verdict(
        monkeypatch,
        tmp_path,
        [
            (StubEvaluation(iface, "can0-first.json"), blocked),
            (StubEvaluation(iface, "can0-second.json"), _permitted()),
        ],
    )
    assert result.ok is False
    assert blocked.summary in result.render()


def test_the_preflight_gate_refuses_a_missing_rid_capture_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Every other input is stubbed to admit, so the absent directory is the only refusal left."""
    config_rid = _config(tmp_path).rid_capture_dir
    result = _preflight_verdict(
        monkeypatch,
        tmp_path,
        [(StubEvaluation(_selected_iface(), "can0.json"), _permitted())],
        rid_dir_exists=False,
    )
    assert result.ok is False
    assert str(config_rid) in result.render()


def test_the_preflight_gate_refuses_when_no_dump_covers_the_selected_channel(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    result = _preflight_verdict(
        monkeypatch, tmp_path, [(StubEvaluation("can9", "can9.json"), _permitted())]
    )
    assert result.ok is False
    assert _selected_iface() in result.render()
