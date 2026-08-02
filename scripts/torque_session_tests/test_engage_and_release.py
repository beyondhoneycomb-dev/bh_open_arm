"""The two torque steps: what the engage measures, and that the release really sends 0xFD.

The runner's whole safety claim about these two steps is that neither can record a pass without
a frame having gone out. So the assertions here are what reached the bus doubles — which motors
each call named, what angle the frame carried, and that the drop happened at all — never that a
method was called.

Both steps refuse on this host, because the single writer that carries one emission to two
channels does not exist. That refusal is asserted first and separately; the rest of the file
injects a writer of the shape the production one must have and runs the steps for real, so the
runner's own assembly, capture and release are proved rather than deferred along with it.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest

from backend.actuation import ArmWriteSlots, BimanualCanWriter
from backend.calibration.schema import MOTOR_ORDER
from backend.endeffector import GRIPPER_SEND_ID, SIDE_LEFT, SIDE_RIGHT, SIDES, spatula_build
from backend.preflight import PreflightReport
from backend.torque_bringup.rig import fitted_motor_names
from contracts.units import Deg, deg_to_rad
from packages.lerobot_robot_openarm.openarm_follower_oa import OaOpenArmFollower
from scripts import rig_session as rig_module
from scripts import torque_session as session
from scripts.torque_session_tests.rig_doubles import (
    LEFT_BASE_DEG,
    RIGHT_BASE_DEG,
    STUB_INTERFACES,
    FakeDamiaoBus,
    FakeLockManager,
    present_deg,
    stub_channels,
    write_stub_binding,
    write_zeroed_calibration,
)
from tests.wp105.conftest import passing_check_results

ENGAGE_STEP = 1
RELEASE_STEP = 2

# The manifest a session is admitted against. The hashes stand in for the PG-SAFE-001 and
# PG-RID-001 PASS evidence; what is under test is that the runner reads a declared manifest
# rather than composing one, so any non-empty hash serves.
MANIFEST = {
    "safe_gate": {
        "gate_id": "PG-SAFE-001",
        "status": "PASS",
        "artifact_hash": "sha256:pg-safe-001-pass",
    },
    "rid_gate": {
        "gate_id": "PG-RID-001",
        "status": "PASS",
        "artifact_hash": "sha256:pg-rid-001-pass",
    },
    "zero_residual": {"within_tolerance": True},
    "gateway_bypass": {"bypass_count": 0},
    "rid9_send_period_sec": 0.001,
}

# Fitted joints on this rig: the spatula build, seven motors and nothing on 0x08.
FITTED = fitted_motor_names(spatula_build())

# How long to wait for the maintainer to get a tick in before asserting it is running. Its own
# period is a fraction of the RID-9 margin, so this is many periods.
MAINTAINER_GRACE_SEC = 0.3


class _Bench:
    """The runner's engage and release over doubled channels, locks, binding and writer."""

    def __init__(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        manifest: bool = True,
        arm: str = session.ARM_LEFT,
    ) -> None:
        """Put a rig's worth of persisted state in a temporary tree and point the runner at it.

        Args:
            tmp_path: Root for the config tree, the capture tree and the manifest.
            monkeypatch: The patcher, for the bus class, the channels, the locks and the writer.
            manifest: Whether a startup manifest is supplied at all.
            arm: Which arm the session runs on. `--arm` accepts either, and the capture's
                arm-major slice is the one index the choice moves.
        """
        self.arm = arm
        self.config_directory = tmp_path / "config" / "openarm"
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        self.config_directory.mkdir(parents=True, exist_ok=True)
        write_stub_binding(self.config_directory)
        for side, robot_id in session.CALIBRATION_ROBOT_IDS.items():
            write_zeroed_calibration(
                self.config_directory / session.CALIBRATION_DIRNAME, robot_id, side
            )

        self.manifest_path: Path | None = None
        if manifest:
            self.manifest_path = tmp_path / "startup.json"
            self.manifest_path.write_text(json.dumps(MANIFEST), encoding="utf-8")

        self.captures_root = tmp_path / "captures"
        self.buses: dict[str, FakeDamiaoBus] = {}
        self.locks = FakeLockManager()
        self.writers: list[BimanualCanWriter] = []
        base = {SIDE_LEFT: LEFT_BASE_DEG, SIDE_RIGHT: RIGHT_BASE_DEG}
        bench = self

        def make_bus(**kwargs: Any) -> FakeDamiaoBus:
            port = str(kwargs["port"])
            side = SIDE_LEFT if port == STUB_INTERFACES[SIDE_LEFT] else SIDE_RIGHT
            bus = FakeDamiaoBus(port=port, base_deg=base[side])
            bench.buses[side] = bus
            return bus

        def make_writer(slots: tuple[ArmWriteSlots, ...]) -> BimanualCanWriter:
            writer = BimanualCanWriter(slots)
            bench.writers.append(writer)
            return writer

        def passing_preflight(*_args: object) -> PreflightReport:
            return PreflightReport(results=passing_check_results())

        monkeypatch.setattr(
            "lerobot.robots.openarm_follower.openarm_follower.DamiaoMotorsBus", make_bus
        )
        monkeypatch.setattr(rig_module, "list_can_channels", stub_channels)
        monkeypatch.setattr(rig_module, "LockManager", lambda: self.locks)
        monkeypatch.setattr(OaOpenArmFollower, "is_calibrated", property(lambda _self: True))
        monkeypatch.setattr(session, "BIMANUAL_CAN_WRITER", make_writer)
        monkeypatch.setattr(session, "_preflight_report", passing_preflight)
        monkeypatch.setattr(session, "_LIVE_SESSION", None)

    @property
    def config(self) -> session.SessionConfig:
        """The session config the steps are called with."""
        return session.SessionConfig(
            arm=self.arm,
            captures_root=self.captures_root,
            rid_capture_dir=self.captures_root / session.RID_CAPTURE_DIRNAME,
            operator="test",
            candump_path=None,
            manifest_path=self.manifest_path,
        )


def _engage(bench: _Bench) -> tuple[bool, str]:
    """Run the engage step the way the worker runs it."""
    return session.run_step(session.STEP_BY_NUMBER[ENGAGE_STEP], bench.config)


def _release(bench: _Bench) -> tuple[bool, str]:
    """Run the release step the way the worker runs it."""
    return session.run_step(session.STEP_BY_NUMBER[RELEASE_STEP], bench.config)


def _capture(bench: _Bench) -> dict[str, Any]:
    """The capture the engage wrote, read back off disk the way its hook reads it."""
    written = bench.captures_root / str(session.STEP_BY_NUMBER[ENGAGE_STEP].capture_dirname)
    files = sorted(written.glob("*.json"))
    assert [path.name for path in files] == [f"{session.ENGAGE_CAPTURE_NAME}.json"]
    return dict(json.loads(files[0].read_text(encoding="utf-8")))


# --- The refusal when the write path is half assembled ---


def test_both_torque_steps_refuse_while_no_single_writer_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The rig binding is not a write path on its own, and half a write path engages nothing.

    The writer is cleared rather than absent, because the shape being judged is a session that
    reaches a torque step with nothing to carry an emission to a channel — and both steps have
    to refuse in it rather than record a pass with no frame behind them.
    """
    monkeypatch.setattr(session, "BIMANUAL_CAN_WRITER", None)
    config = session.SessionConfig(
        arm=session.ARM_LEFT,
        captures_root=tmp_path,
        rid_capture_dir=tmp_path / "rid",
        operator="test",
        candump_path=None,
    )
    for number in (ENGAGE_STEP, RELEASE_STEP):
        passed, detail = session.run_step(session.STEP_BY_NUMBER[number], config)
        assert passed is False
        assert "단일 작성자" in detail
        assert detail.startswith(f"{session.STEP_BY_NUMBER[number].key}:")
    assert list(tmp_path.rglob("*.json")) == []


# --- The engage, for real, over the injected writer ---


def test_the_engage_writes_a_capture_of_what_reached_the_bus(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The capture is the measured ids, the measured pose, and the frame the writer emitted.

    Every number in it comes off the rig: the ids from the fitted profile, the pose from the
    bus, the frame from the single writer's own emission. A producer that composed any of them
    would be feeding its own hook a value nobody measured.
    """
    bench = _Bench(tmp_path, monkeypatch)
    passed, detail = _engage(bench)
    assert passed is True, detail

    capture = _capture(bench)
    block = capture[session.CAPTURE_RIG_ENGAGE_BLOCK]
    assert block[session.CAPTURE_SEND_IDS_KEY] == list(spatula_build().motor_send_ids)
    assert GRIPPER_SEND_ID not in block[session.CAPTURE_SEND_IDS_KEY]
    expected = [deg_to_rad(Deg(angle)).value for angle in present_deg(LEFT_BASE_DEG, len(FITTED))]
    assert block[session.CAPTURE_PRESENT_KEY] == pytest.approx(expected)
    frame = block[session.CAPTURE_FRAME_KEY]
    assert len(frame) == len(FITTED)
    assert [command["q"] for command in frame] == pytest.approx(expected)
    assert all(command["kp"] > 0.0 for command in frame)
    assert capture[session.CAPTURE_INTERFACES_KEY] == STUB_INTERFACES
    _release(bench)


@pytest.mark.parametrize(
    ("arm", "base_deg"),
    [(SIDE_LEFT, LEFT_BASE_DEG), (SIDE_RIGHT, RIGHT_BASE_DEG)],
    ids=[SIDE_LEFT, SIDE_RIGHT],
)
def test_the_capture_records_the_selected_arms_own_half_of_the_frame(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, arm: str, base_deg: float
) -> None:
    """`--arm` accepts either, and the capture's arm-major slice is the one index that moves.

    The emission is left-major and `BIMANUAL_BATCH_WIDTH` wide, so a right-arm session reads its
    own seven commands from the second half. Slicing the first half regardless records the other
    arm's angles as this arm's, and the wp105 acceptance hooks judge that record — so a right-arm
    session would be judged against a frame that never went to it.

    The two arms sit at different base angles here for exactly this reason. At the URDF zero they
    would be numerically identical and no assertion could separate a right slice from a wrong one.
    """
    bench = _Bench(tmp_path, monkeypatch, arm=arm)

    passed, detail = _engage(bench)
    assert passed is True, detail

    block = _capture(bench)[session.CAPTURE_RIG_ENGAGE_BLOCK]
    expected = [deg_to_rad(Deg(angle)).value for angle in present_deg(base_deg, len(FITTED))]
    assert block[session.CAPTURE_PRESENT_KEY] == pytest.approx(expected)
    assert [command["q"] for command in block[session.CAPTURE_FRAME_KEY]] == pytest.approx(expected)

    # And the other arm was never energized: the fan-out reaches its channel, the enable does not.
    other = SIDE_RIGHT if arm == SIDE_LEFT else SIDE_LEFT
    assert bench.buses[arm].enabled_motors == [list(FITTED)]
    assert bench.buses[other].enabled_motors == []

    _release(bench)


def test_the_engage_frame_carries_the_left_arm_angles_to_the_left_channel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The two arms sit at different angles, so a half sent to the wrong channel is visible.

    can0 is the left arm by physical measurement and the binding is what says which interface
    that is. A frame assembled the other way round moves both arms, to each other's targets.
    """
    bench = _Bench(tmp_path, monkeypatch)
    passed, detail = _engage(bench)
    assert passed is True, detail

    # Every joint of both halves, not just the first. A half sent in the wrong order carries the
    # right channel's angles and the wrong joint's, and only a per-joint comparison sees it.
    for side, base in ((SIDE_LEFT, LEFT_BASE_DEG), (SIDE_RIGHT, RIGHT_BASE_DEG)):
        sent = bench.buses[side].sent[-1]
        for name, angle in zip(FITTED, present_deg(base, len(FITTED)), strict=True):
            assert sent[name][2] == pytest.approx(angle)
    _release(bench)


def test_the_engage_addresses_no_motor_the_rig_does_not_carry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Read, enable and write all name their motors, and 0x08 is not among them.

    Motor 0x08 answered 0 of 20 polls on both arms here, and sixteen unanswered frames took both
    channels to ERROR-PASSIVE — which degrades the seven joints that are present.
    """
    bench = _Bench(tmp_path, monkeypatch)
    passed, detail = _engage(bench)
    assert passed is True, detail

    unfitted = MOTOR_ORDER[-1]
    for side in SIDES:
        bus = bench.buses[side]
        for motors in bus.read_motors:
            assert motors is not None
            assert unfitted not in motors
        for motors in bus.enabled_motors:
            assert unfitted not in motors
        for sent in bus.sent:
            assert unfitted not in sent
    assert bench.buses[SIDE_LEFT].enabled_motors == [list(FITTED)]
    assert bench.buses[SIDE_RIGHT].enabled_motors == []
    _release(bench)


def test_the_engage_leaves_the_hold_being_re_sent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An engaged arm is an arm being refreshed, or it is an arm falling.

    Past the RID-9 no-send ceiling the motor stops applying the last MIT command. Between this
    step and the release step the worker sleeps, so the re-send has to come from somewhere else.
    """
    bench = _Bench(tmp_path, monkeypatch)
    passed, detail = _engage(bench)
    assert passed is True, detail

    live = session._LIVE_SESSION
    assert live is not None
    assert live.maintainer.is_alive()
    writes = bench.writers[-1].write_count
    time.sleep(MAINTAINER_GRACE_SEC)
    assert bench.writers[-1].write_count > writes
    assert live.maintainer.failure is None
    _release(bench)


# --- The release, for real: a frame goes out or nothing is recorded ---


def test_the_release_drops_the_fitted_motors_and_stops_the_re_send(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Recording a drop that never reached a motor ends a session green on an energized arm.

    The maintainer is stopped first because `disable_torque` and a MIT write share one socket: a
    drop racing a re-send is a frame going out after the motors were told to let go.
    """
    bench = _Bench(tmp_path, monkeypatch)
    assert _engage(bench)[0] is True
    maintainer = session._LIVE_SESSION.maintainer  # type: ignore[union-attr]

    passed, detail = _release(bench)

    assert passed is True, detail
    assert bench.buses[SIDE_LEFT].disabled_motors == [list(FITTED)]
    assert bench.buses[SIDE_RIGHT].disabled_motors == []
    assert maintainer.is_alive() is False
    # The counter the scheduler's single-write guard reads, against the frames the channels
    # actually received. Comparing it to the writer's own record of what it was handed would
    # only ever agree with itself; a fan-out that dropped a channel shows up here.
    assert bench.writers[-1].write_count == len(bench.buses[SIDE_LEFT].sent)
    assert bench.writers[-1].write_count == len(bench.buses[SIDE_RIGHT].sent)
    for send_id in spatula_build().motor_send_ids:
        assert f"{send_id:#04x}" in detail
    assert session._LIVE_SESSION is None
    assert bench.locks.releases == 1


def test_the_release_closes_the_channels_without_cutting_torque_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The bus's own disconnect cuts torque over every registered motor, 0x08 included."""
    bench = _Bench(tmp_path, monkeypatch)
    assert _engage(bench)[0] is True
    _release(bench)

    for side in SIDES:
        assert bench.buses[side].disconnected_cutting_torque == [False]
    assert bench.buses[SIDE_LEFT].disabled_motors == [list(FITTED)]


def test_the_release_alone_assembles_and_drops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A selection that runs the release alone must still put a frame on the bus.

    Refusing for want of an engage in this process strands an operator whose arm was energized
    by something else, and this is the step whose whole content is them taking its weight.
    """
    bench = _Bench(tmp_path, monkeypatch)
    assert session._LIVE_SESSION is None

    passed, detail = _release(bench)

    assert passed is True, detail
    assert bench.buses[SIDE_LEFT].disabled_motors == [list(FITTED)]
    assert bench.buses[SIDE_LEFT].enabled_motors == []
    assert bench.locks.releases == 1


def test_the_release_alone_drops_with_no_startup_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The release is gated on nothing the engage needed.

    `disengage` reads the support declaration, the fitted id set and the bus. Building the engage's
    two authorizations to reach it would refuse the drop for want of a permission it never reads,
    and this path exists for an arm a dead process left energized — with both channels already
    open by the time the refusal landed. The manifest gates the engage and must not reach here.
    """
    bench = _Bench(tmp_path, monkeypatch, manifest=False)
    assert session._LIVE_SESSION is None

    passed, detail = _release(bench)

    assert passed is True, detail
    assert bench.buses[SIDE_LEFT].disabled_motors == [list(FITTED)]
    assert bench.buses[SIDE_LEFT].enabled_motors == []
    assert bench.locks.releases == 1


def test_a_maintenance_loop_that_will_not_stop_does_not_hold_up_the_drop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tick blocked on the bus must not keep torque on.

    `canbus.send()` blocks while the transmit buffer stays full, which is where a channel sits
    once it is ERROR-PASSIVE with nothing acknowledging — measured on both channels of this bench.
    An unbounded join there hangs the release forever with the arm energized and the operator
    holding it, and `run_step` cannot see it because a hang is not an exception.

    0xFD reaching the motors is what matters; a stray re-send afterwards moves nothing, since a
    MIT frame arriving at a disabled motor is the same no-op the engage's proving tick relies on.
    """
    monkeypatch.setattr(session, "HOLD_STOP_JOIN_TIMEOUT_SEC", 0.05)
    bench = _Bench(tmp_path, monkeypatch)
    _engage(bench)
    live = session._LIVE_SESSION
    assert live is not None

    # A loop that never observes the stop event: exactly what a blocked send looks like. The join
    # returns without the thread having ended, which is what `Thread.join(timeout=...)` does on a
    # thread stuck in a syscall.
    def _join_that_times_out(timeout: float | None = None) -> None:
        """Return having waited, with the thread still running."""

    def _still_running() -> bool:
        """Report the loop as alive, the way a blocked tick leaves it."""
        return True

    monkeypatch.setattr(live.maintainer, "join", _join_that_times_out)
    monkeypatch.setattr(live.maintainer, "is_alive", _still_running)

    passed, detail = _release(bench)

    assert passed is True, detail
    assert bench.buses[SIDE_LEFT].disabled_motors == [list(FITTED)]
    assert "버스를 놓지 않았다" in detail


# --- Refusals the engage owes before it energizes anything ---


def test_no_startup_manifest_refuses_before_anything_is_assembled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The PG-SAFE-001 PASS hash is a declared field, and a runner that filled it in is the gate.

    The refusal has to land before the channels open, because a session that got as far as
    holding locks has already told the operator it is going ahead.
    """
    bench = _Bench(tmp_path, monkeypatch, manifest=False)

    passed, detail = _engage(bench)

    assert passed is False
    assert "매니페스트" in detail
    assert bench.buses == {}
    assert bench.locks.acquired == []


def test_a_rig_record_declaring_the_absent_gripper_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The admission gate reads the default profile; the engage polls the record.

    A record that disagreed with the gate would reach the bus unjudged, so the engage re-applies
    the same rule to the record it will actually use.
    """
    from backend.endeffector import RigEndEffectors, gripper_build, rig_path, save_rig

    bench = _Bench(tmp_path, monkeypatch)
    save_rig(
        rig_path(bench.config_directory),
        RigEndEffectors(left=gripper_build(), right=gripper_build()),
    )

    passed, detail = _engage(bench)

    assert passed is False
    assert f"{GRIPPER_SEND_ID:#04x}" in detail
    assert bench.buses == {}


def test_a_record_of_the_fitted_build_is_read_and_used(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The record is read when it exists. Without this the refusal above could be a hardcoded no."""
    from backend.endeffector import RigEndEffectors, rig_path, save_rig

    bench = _Bench(tmp_path, monkeypatch)
    save_rig(
        rig_path(bench.config_directory),
        RigEndEffectors(left=spatula_build(), right=spatula_build()),
    )

    passed, detail = _engage(bench)

    assert passed is True, detail
    assert bench.buses[SIDE_LEFT].enabled_motors == [list(FITTED)]
    _release(bench)


def test_a_channel_the_binding_does_not_resolve_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A binding that silently followed a renumbered bus enforces one arm's limits on the other."""
    bench = _Bench(tmp_path, monkeypatch)
    monkeypatch.setattr(rig_module, "list_can_channels", tuple)

    passed, detail = _engage(bench)

    assert passed is False
    assert "Re-identify" in detail
    assert bench.buses == {}


def test_the_zero_residual_in_the_capture_is_recomputed_from_the_calibration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The hook refuses a capture taken on an out-of-tolerance zero, so the verdict must be real.

    The calibration carries its own verdict field; this reads the recorded angles and runs them
    through the one definition of the tolerance, so a file whose verdict disagreed with its own
    numbers is judged on the numbers.
    """
    from backend.calibration.atomic_io import (
        calibration_path_for,
        load_calibration,
        save_calibration_atomic,
    )
    from backend.calibration.schema import MOTOR_COUNT, ZERO_RESIDUAL_TOLERANCE_DEG

    bench = _Bench(tmp_path, monkeypatch)
    directory = bench.config_directory / session.CALIBRATION_DIRNAME
    path = calibration_path_for(directory, session.CALIBRATION_ROBOT_IDS[SIDE_LEFT])
    calibration = load_calibration(path)
    calibration.motor_zero_raw = [ZERO_RESIDUAL_TOLERANCE_DEG * 10.0] * MOTOR_COUNT
    save_calibration_atomic(path, calibration)

    passed, detail = _engage(bench)

    assert passed is False
    assert "영점 잔차" in detail
    # The hook refused the capture, so nothing was written into the operator's tree.
    assert list(bench.captures_root.rglob("*.json")) == []
    _release(bench)
