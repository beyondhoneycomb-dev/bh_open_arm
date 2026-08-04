"""The production rig assembly: which channel, whose pose, which motors, and nothing energized.

`build_engage_bus` is proved over doubles in `test_rig_engage.py`. What is proved here is the
assembly that hands it the four things it borrows — and every one of those is a place a wrong
answer is invisible at runtime: an arm opened on the wrong channel commands the other arm's
joints, a scheduler stood up on zeros holds a brakeless arm at the horizontal, and a writer
given the full frozen layout addresses a motor nobody answers on.

The bus, the channel locks and the persisted binding are doubles; the assembly and the single
writer are the production ones. The writer is deliberately not doubled — it is the thing whose
output is the frame that reaches a motor, and a second implementation of the split would make
every assertion about which channel got which half an assertion about that implementation.

The interfaces the stub binding resolves are deliberately not `can0`/`can1`, because those are
what the side placeholder guesses and an arm that opened on them would pass whether or not it
ever read the record.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import pytest
from lerobot.motors.damiao import DamiaoMotorsBus

from backend.actuation import ArmWriteSlots, BimanualCanWriter, EmissionLabel
from backend.calibration.schema import MOTOR_ORDER
from backend.endeffector import (
    GRIPPER_SEND_ID,
    SIDE_LEFT,
    SIDE_RIGHT,
    SIDES,
    RigEndEffectors,
    gripper_build,
    spatula_build,
)
from backend.preflight import PreflightReport
from backend.torque_bringup import (
    SEND_ID_BY_MOTOR,
    GuardedTorqueOn,
    TorqueOnManifest,
    assert_safe_hold,
)
from backend.torque_bringup.rig import fitted_motor_names
from backend.torque_bringup.stop_path import assert_stop_path_cuts_no_torque, stop_path_files
from contracts.units import Deg, deg_to_rad
from packages.lerobot_robot_openarm.openarm_follower_oa import PORT_BY_SIDE, OaOpenArmFollower
from scripts import rig_session as rig_module
from scripts.rig_session import (
    DAMIAO_BUS_LOGGER,
    PACKET_DROP_PREFIX,
    RigArmBus,
    RigAssemblyError,
    arm_write_slots,
    build_rig_session,
    resolve_arm_interfaces,
)
from scripts.torque_session_tests.rig_doubles import (
    LEFT_BASE_DEG,
    RIGHT_BASE_DEG,
    STUB_INTERFACES,
    UNFITTED_SLOT_DEG,
    FakeDamiaoBus,
    FakeLockManager,
    RefusingLockManager,
    present_deg,
    stub_channels,
    write_stub_binding,
)

# The calibration instance ids the assembly loads each arm's zero under. The runner's own names,
# restated here because the assembly takes them as an argument rather than knowing them.
ROBOT_IDS = {SIDE_LEFT: "openarm_left", SIDE_RIGHT: "openarm_right"}

# How many joints the fitted spatula build puts on each bus.
FITTED_JOINTS = len(fitted_motor_names(spatula_build()))

# Ticks the engage drives: one with torque still off to prove the path carries this pose, and
# one immediately after 0xFC.
ENGAGE_TICKS = 2

# Agreement tolerance for a degree-to-radian round trip.
ANGLE_TOLERANCE_RAD = 1e-12

_SKIP_REASON = (
    "the operator-in-the-loop guarded torque-ON: one person supporting a brakeless arm, both "
    "channels bound and powered, a PG-SAFE-001 PASS declared in a startup manifest, and "
    "./scripts/torque_session.sh --run driving it (12 FR-SAF-075, 16 M-2). Nothing offline can "
    "stand in for it, and it never runs without a human present"
)


class _Bench:
    """One assembled production rig over doubles: two buses, one lock manager, one writer."""

    def __init__(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        end_effectors: RigEndEffectors | None = None,
        unanswered: tuple[str, ...] = (),
        stale_cache: bool = False,
        report_drops: bool = True,
        locks: FakeLockManager | None = None,
    ) -> None:
        """Point the assembly at doubles and record what it built.

        Args:
            tmp_path: Config and calibration root for this bench.
            monkeypatch: The patcher, for the bus class and the channel enumeration.
            end_effectors: What each arm carries; a spatula on both otherwise.
            unanswered: Fitted motors the left bus answers no state for.
            stale_cache: Whether a silent motor carries its last real angle instead of the
                zeroed cache — the state a motor that replied and then stopped leaves behind.
            report_drops: Whether the bus writes the drop record at all, so the backstop can
                be exercised on its own.
            locks: The lock manager the assembly is given; a granting one otherwise.
        """
        self.config_directory = tmp_path
        self.calibration_dir = tmp_path / "calibration"
        self.end_effectors = (
            end_effectors
            if end_effectors is not None
            else RigEndEffectors(left=spatula_build(), right=spatula_build())
        )
        self.interfaces = write_stub_binding(tmp_path)
        self.buses: dict[str, FakeDamiaoBus] = {}
        self.locks = locks if locks is not None else FakeLockManager()
        self.writers: list[BimanualCanWriter] = []
        base = {SIDE_LEFT: LEFT_BASE_DEG, SIDE_RIGHT: RIGHT_BASE_DEG}
        bench = self

        def make_bus(**kwargs: Any) -> FakeDamiaoBus:
            port = str(kwargs["port"])
            side = SIDE_LEFT if port == bench.interfaces[SIDE_LEFT] else SIDE_RIGHT
            bus = FakeDamiaoBus(
                port=port,
                base_deg=base[side],
                unanswered=unanswered if side == SIDE_LEFT else (),
            )
            bus.stale_cache = stale_cache
            bus.report_drops = report_drops
            bench.buses[side] = bus
            return bus

        monkeypatch.setattr(
            "lerobot.robots.openarm_follower.openarm_follower.DamiaoMotorsBus", make_bus
        )
        monkeypatch.setattr(rig_module, "list_can_channels", stub_channels)
        monkeypatch.setattr(rig_module, "LockManager", lambda: self.locks)
        monkeypatch.setattr(OaOpenArmFollower, "is_calibrated", property(lambda _self: True))

    def make_writer(self, slots: tuple[ArmWriteSlots, ...]) -> BimanualCanWriter:
        """Build the production single writer from the per-arm slot plan and keep it."""
        writer = BimanualCanWriter(slots)
        self.writers.append(writer)
        return writer

    def build(self) -> Any:
        """Run the production assembly over this bench."""
        return build_rig_session(
            make_can_writer=self.make_writer,
            end_effectors=self.end_effectors,
            calibration_dir=self.calibration_dir,
            robot_ids=ROBOT_IDS,
            config_directory=self.config_directory,
        )


def _engage(session: Any, side: str, preflight: Any, manifest: Any) -> Any:
    """Run one guarded torque-ON over one arm of an assembled session."""
    return GuardedTorqueOn(
        session.rig.for_side(side), session.pair.left_arm._end_effector, preflight, manifest
    ).engage()


# --- Which channel is which arm ---


def test_the_binding_record_is_what_each_arm_opens_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The arms are indistinguishable by CAN id, so the channel is read and never derived.

    The stub record resolves to interfaces the side placeholder would never produce, so an arm
    that fell back to `PORT_BY_SIDE` is visible rather than indistinguishable from a correct one.
    """
    bench = _Bench(tmp_path, monkeypatch)
    session = bench.build()

    assert dict(session.interfaces) == STUB_INTERFACES
    for side in SIDES:
        assert bench.buses[side].port == STUB_INTERFACES[side]
        assert bench.buses[side].port != PORT_BY_SIDE[side]
    # And the lock the connect guard checked is the same channel the socket opened on.
    assert bench.locks.acquired == [[STUB_INTERFACES[side] for side in SIDES]]


def test_a_role_whose_channel_is_absent_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_stub_binding(tmp_path)
    monkeypatch.setattr(rig_module, "list_can_channels", tuple)

    with pytest.raises(RigAssemblyError, match="Re-identify"):
        resolve_arm_interfaces(tmp_path)


def test_an_unreadable_binding_record_is_refused(tmp_path: Path) -> None:
    with pytest.raises(RigAssemblyError, match="nothing to fall back to"):
        resolve_arm_interfaces(tmp_path)


# --- What each half of an emission addresses ---


def test_the_write_plan_leaves_the_unfitted_slot_unaddressed() -> None:
    """Every slot of the emission is covered and the one no motor answers on names nothing.

    The emission is the frozen eight-per-arm layout; the fitted spatula puts a motor behind
    seven of them. A plan that named the eighth would put a frame on `0x08`, and sixteen
    unanswered frames took both channels to ERROR-PASSIVE on this bench.
    """
    buses = {side: FakeDamiaoBus(port=STUB_INTERFACES[side], base_deg=0.0) for side in SIDES}
    slots = arm_write_slots(buses, RigEndEffectors(left=spatula_build(), right=spatula_build()))

    assert len(slots) == len(SIDES)
    for arm in slots:
        assert arm.slot_names[:-1] == MOTOR_ORDER[:-1]
        assert arm.slot_names[-1] is None
    assert sum(len(arm.slot_names) for arm in slots) == len(MOTOR_ORDER) * len(SIDES)
    # And each half is paired with its own side's bus, in the emission's arm-major order. The
    # writer sends the first half on the first entry's bus, so this pairing is the whole
    # statement of which arm the left half reaches — nothing on the bus can report it wrong.
    for side, arm in zip(SIDES, slots, strict=True):
        assert arm.bus is buses[side]


def test_the_write_plan_addresses_the_gripper_when_one_is_fitted() -> None:
    """The plan follows the tool. Without this the unfitted marker could be a hardcoded None."""
    buses = {side: FakeDamiaoBus(port=STUB_INTERFACES[side], base_deg=0.0) for side in SIDES}
    slots = arm_write_slots(buses, RigEndEffectors(left=gripper_build(), right=gripper_build()))

    for arm in slots:
        assert arm.slot_names == MOTOR_ORDER


def test_a_plan_that_does_not_cover_the_emission_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A plan narrower than the frame leaves joints uncommanded; a wider one reads past its end."""
    monkeypatch.setattr(rig_module, "MOTOR_ORDER", MOTOR_ORDER[:-1])
    buses = {side: FakeDamiaoBus(port=STUB_INTERFACES[side], base_deg=0.0) for side in SIDES}

    with pytest.raises(RigAssemblyError, match="one emission is"):
        arm_write_slots(buses, RigEndEffectors(left=spatula_build(), right=spatula_build()))


# --- The cached hold the scheduler starts on ---


def test_the_scheduler_starts_holding_where_the_arms_are(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tick with an empty mailbox emits the cached hold, and zeros there are the horizontal.

    The arm hangs at the URDF zero and its end effector sits at z = 0.904 m, so a scheduler
    stood up on a zero vector would command every joint to the horizontal the first time a tick
    found nothing published — on an arm with no brake.
    """
    bench = _Bench(tmp_path, monkeypatch)
    session = bench.build()

    emission = session.rig.maintain_hold()

    assert emission.label is not EmissionLabel.ACCEPTED_TARGET
    assert_safe_hold(emission.batch)
    emitted = [command.q.value for command in emission.batch]
    expected: list[float] = []
    for base in (LEFT_BASE_DEG, RIGHT_BASE_DEG):
        expected.extend(present_deg(base, FITTED_JOINTS))
        expected.append(UNFITTED_SLOT_DEG)
    assert emitted == pytest.approx(
        [deg_to_rad(Deg(angle)).value for angle in expected], abs=ANGLE_TOLERANCE_RAD
    )
    assert any(angle != 0.0 for angle in emitted)


def test_a_fitted_motor_that_answered_nothing_refuses_the_assembly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A substituted zero becomes the frame a lapsed tick holds on, and zero is the hang.

    The bus does not report a silent motor by omission: it returns the zeroed cache entry with
    every field present, in the same shape a reply has. So the number that reaches the assembly
    is 0.0 deg, which on this arm is the pose it hangs in — plausible enough that a hold built
    from it satisfies every check downstream, because each of them compares it to a value derived
    from it. Held at torque-on with the arm raised, that hold drives it down out of the
    operator's hands.
    """
    unread = MOTOR_ORDER[3]
    bench = _Bench(tmp_path, monkeypatch, unanswered=(unread,))

    with pytest.raises(RigAssemblyError, match=unread):
        bench.build()

    # Nothing energized, both channels closed, both locks back.
    for side in SIDES:
        assert bench.buses[side].enabled_motors == []
        assert bench.buses[side].is_connected is False
    assert bench.locks.releases == 1


def test_a_motor_that_went_silent_after_answering_once_is_still_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The stale-cache case, which the all-zero backstop cannot see.

    `_process_response` updates the cache, so a motor that replied and then stopped carries its
    last real angle rather than a zero — the mid-session ERROR-PASSIVE state both channels reached
    on this bench. That entry is indistinguishable from a reading by its value alone, and the drop
    record is the only thing that separates them.
    """
    unread = MOTOR_ORDER[3]
    bench = _Bench(tmp_path, monkeypatch, unanswered=(unread,), stale_cache=True)

    with pytest.raises(RigAssemblyError, match=unread):
        bench.build()

    assert bench.buses[SIDE_LEFT].enabled_motors == []


def test_a_zeroed_state_with_no_drop_record_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The backstop, which does not depend on the vendor's logging.

    The drop record is a log line, and a log line is a contract the library can change without
    changing an API. An all-zero state is the cache initialiser whatever the logger did: a powered
    motor reports its temperatures in degrees Celsius, so ambient alone puts them above zero.
    """
    unread = MOTOR_ORDER[3]
    bench = _Bench(tmp_path, monkeypatch, unanswered=(unread,), report_drops=False)

    with pytest.raises(RigAssemblyError, match=unread):
        bench.build()

    assert bench.buses[SIDE_LEFT].enabled_motors == []


def test_the_installed_bus_still_answers_for_a_motor_that_said_nothing() -> None:
    """The vendor contract the read filter is built on, read off the installed library.

    Two facts hold this together and neither is an API: `sync_read_all_states` returns an entry
    for every motor asked for — taken from a cache initialised to zero — and a motor that did not
    reply is reported only as a log record. A release that changed either would leave the filter
    running against a signal that no longer arrives, with nothing failing.

    Pinned against the source rather than a live bus, because establishing it on hardware means
    polling a motor that is not there.
    """
    source = Path(inspect.getfile(DamiaoMotorsBus)).read_text(encoding="utf-8")

    # The cache is what a silent motor's entry comes from, and it starts at zero.
    assert '"position": 0.0,' in source
    # Every requested motor gets an entry, whether it answered or not.
    assert "result[motor] = self._last_known_states[motor].copy()" in source
    # A drop reaches the caller as this record and nothing else.
    assert f'logger.warning(f"{PACKET_DROP_PREFIX}' in source
    assert DamiaoMotorsBus.__module__ == DAMIAO_BUS_LOGGER

    # And no return-valued or counted alternative exists to read instead.
    assert "def drop_count" not in source
    assert "def enable_drop_counting" not in source


def test_a_channel_lock_held_elsewhere_refuses_before_any_socket_opens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bench = _Bench(tmp_path, monkeypatch, locks=RefusingLockManager())

    with pytest.raises(RigAssemblyError, match="another-writer"):
        bench.build()

    assert bench.buses == {} or all(not bus.is_connected for bus in bench.buses.values())


# --- Nothing is energized by assembling, and the deadman is live when it returns ---


def test_assembling_commands_no_torque_and_arms_the_deadman(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Assembly asks for no torque, and the first tick must not read a dead lease.

    Asks for none, but does not leave the arms dead: the bus handshake enables every fitted
    motor, so what these assertions establish is that no command followed it, not that the
    rig is safe to let go of.

    A first tick on an un-renewed lease emits the cached hold instead of the target the engage
    just published, and on a brakeless arm the cached frame is a pose from before this session.
    """
    bench = _Bench(tmp_path, monkeypatch)
    session = bench.build()

    for side in SIDES:
        assert bench.buses[side].enabled_motors == []
        assert bench.buses[side].disabled_motors == []
        assert bench.buses[side].is_connected is True
    emission = session.rig.maintain_hold()
    assert emission.reason.value != "lease_expired"


def test_the_read_at_assembly_never_addresses_the_unfitted_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Motor 0x08 answered 0 of 20 polls here, and a bare read walks all eight registered names."""
    bench = _Bench(tmp_path, monkeypatch)
    bench.build()

    for side in SIDES:
        for motors in bench.buses[side].read_motors:
            assert motors is not None, "a read that named no motors walks the unfitted id"
            assert MOTOR_ORDER[-1] not in motors


# --- The engage, end to end, over the production assembly ---


def test_the_engage_frame_reaches_both_channels_and_holds_the_reported_pose(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    passing_preflight: PreflightReport,
    passing_manifest: TorqueOnManifest,
) -> None:
    """One emission, one counted write, each arm's fitted slots on its own channel.

    This is the whole claim of the assembly: the frame that reaches a motor is the one the
    enforcement point decided, split to the channel the binding says that arm is on, with the
    unfitted slot sent nowhere.
    """
    bench = _Bench(tmp_path, monkeypatch)
    session = bench.build()
    result = _engage(session, SIDE_LEFT, passing_preflight, passing_manifest)

    assert result.send_ids == spatula_build().motor_send_ids
    assert set(result.commanded_displacement_rad()) == {0.0}

    writer = bench.writers[-1]
    assert writer.write_count == ENGAGE_TICKS
    fitted = fitted_motor_names(spatula_build())
    for side, base in ((SIDE_LEFT, LEFT_BASE_DEG), (SIDE_RIGHT, RIGHT_BASE_DEG)):
        sent = bench.buses[side].sent[-1]
        assert len(bench.buses[side].sent) == writer.write_count
        assert sorted(sent) == sorted(fitted)
        assert MOTOR_ORDER[-1] not in sent
        # Every joint, not just the first. A permuted half is the same width, the same count and
        # the same set of names, so only a per-joint comparison separates it from a correct one —
        # and each joint's reported angle differs from its neighbour's by one step.
        for angle, name in zip(present_deg(base, len(fitted)), fitted, strict=True):
            assert sent[name][2] == pytest.approx(angle)
        # The names that received a frame are exactly the fitted send ids. Asserting names alone
        # leaves the name-to-id join unchecked, and `0x08` is the id nothing answers on.
        assert (
            tuple(sorted(SEND_ID_BY_MOTOR[name] for name in sent)) == spatula_build().motor_send_ids
        )
        assert GRIPPER_SEND_ID not in {SEND_ID_BY_MOTOR[name] for name in sent}
    # The two arms carry different angles, so a half sent to the wrong channel is visible.
    left_first = bench.buses[SIDE_LEFT].sent[-1][fitted[0]][2]
    right_first = bench.buses[SIDE_RIGHT].sent[-1][fitted[0]][2]
    assert left_first != right_first


def test_the_engage_enables_only_the_fitted_motors_of_the_engaged_arm(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    passing_preflight: PreflightReport,
    passing_manifest: TorqueOnManifest,
) -> None:
    bench = _Bench(tmp_path, monkeypatch)
    session = bench.build()
    _engage(session, SIDE_LEFT, passing_preflight, passing_manifest)

    assert bench.buses[SIDE_LEFT].enabled_motors == [list(fitted_motor_names(spatula_build()))]
    assert bench.buses[SIDE_RIGHT].enabled_motors == []


def test_the_disengage_drops_only_the_fitted_motors_through_the_rename(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    passing_preflight: PreflightReport,
    passing_manifest: TorqueOnManifest,
) -> None:
    """`drop_torque` is the bus's `disable_torque` under the name the engage tree may hold.

    The names matter as much as the rename: a drop addressed to `0x08` is an unanswered frame,
    and the drop is the last call an operator makes with the arm's weight in their hands.
    """
    bench = _Bench(tmp_path, monkeypatch)
    session = bench.build()
    guarded = GuardedTorqueOn(
        session.rig.for_side(SIDE_LEFT), spatula_build(), passing_preflight, passing_manifest
    )
    guarded.engage()

    assert guarded.disengage(arm_supported=True) == spatula_build().motor_send_ids
    assert bench.buses[SIDE_LEFT].disabled_motors == [list(fitted_motor_names(spatula_build()))]
    assert bench.buses[SIDE_RIGHT].disabled_motors == []


def test_closing_the_session_sends_nothing_and_gives_the_locks_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The bus's own disconnect disables torque over every registered motor. Both halves are wrong.

    Dropping torque on an arm nobody is supporting is a fall rather than a stop, and the walk
    covers the id nothing answers on.
    """
    bench = _Bench(tmp_path, monkeypatch)
    session = bench.build()
    session.close()

    for side in SIDES:
        assert bench.buses[side].disconnected_cutting_torque == [False]
        assert bench.buses[side].disabled_motors == []
        assert bench.buses[side].is_connected is False
    assert bench.locks.releases == 1


# --- The scan the rename must not have broken ---


def test_the_engage_tree_still_contains_no_torque_cut() -> None:
    """The rename put `disable_torque` in the tree that holds the bus, not the one that engages.

    The scan is a precondition of engaging, and it reports what it found and never how much it
    parsed — so the file count is asserted too: an empty scan over a tree it never opened returns
    the same empty list a clean tree does.
    """
    scanned = stop_path_files()

    assert assert_stop_path_cuts_no_torque() == ()
    assert len(scanned) >= 1
    assert any(path.name == "rig.py" for path in scanned)


def test_the_adapter_passes_the_names_it_was_given_and_no_others() -> None:
    """Every call names its motors. The bare default walks the id nothing answers on."""
    bus = FakeDamiaoBus(port=STUB_INTERFACES[SIDE_LEFT], base_deg=LEFT_BASE_DEG)
    adapter = RigArmBus(bus)
    fitted = list(fitted_motor_names(spatula_build()))

    adapter.drop_torque(fitted)
    adapter.enable_torque(fitted)
    adapter.sync_read_all_states(fitted)

    assert bus.disabled_motors == [fitted]
    assert bus.enabled_motors == [fitted]
    assert bus.read_motors == [fitted]
    assert GRIPPER_SEND_ID not in spatula_build().motor_send_ids
    assert MOTOR_ORDER[-1] in adapter.motors, "registration is the bus's, not a filtered copy"


# --- The deferred acceptance nothing offline can stand in for ---


@pytest.mark.skip(reason=_SKIP_REASON)
def test_deferred_operator_in_the_loop_guarded_torque_on() -> None:
    """The first live run of this assembly, with a person supporting the arm.

    What it will confirm, in the order the session runs it: both follower roles resolve to a
    channel present at that moment; the seven fitted motors on the engaged arm answer a
    present-pose read and `0x08` is never polled; the write path carries this session's own
    pose with torque still off; 0xFC leaves and the frame behind it is the same decision; the
    arm does not move when torque comes on; the hold is re-sent inside the RID-9 no-send margin
    for the whole session; and the release drops exactly `0x01..0x07` with the operator holding
    the weight. The capture it writes is what
    `test_rig_engage.py::test_deferred_real_rig_engage_holds_the_fitted_motors` then judges.
    """
