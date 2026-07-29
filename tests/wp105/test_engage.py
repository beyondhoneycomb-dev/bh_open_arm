"""The guarded engage: what it refuses, which motors it addresses, and how it is released.

Five refusals stand between an authorized session and 0xFC, and each is checked here by
making it fire: a blocked preflight precondition (named in the message), a motor set that is
not the fitted one in either direction, a fitted tool that declares no motors at all, a torque
cut reachable from the stop path, and a disengage on an unsupported arm. The sixth property is
positive — the engage addresses exactly the ids the fitted tool declares, which on this bench
is seven and never eight.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.endeffector import GRIPPER_SEND_ID, EndEffectorProfile, ToolDefinition
from backend.preflight import PreflightCheck, PreflightReport, TorqueOnBlockedError
from backend.torque_bringup import (
    TORQUE_BRINGUP_ROOT,
    FittedMotorMismatchError,
    GuardedTorqueOn,
    TorqueCutOnStopPathError,
    TorqueDisengageRefusedError,
    TorqueOnManifest,
    assert_stop_path_cuts_no_torque,
    find_torque_cut_on_stop_path,
)
from backend.torque_bringup import sequence as sequence_module
from contracts.units import Rad
from tests.wp105.conftest import RecordingEngageBus, pose_for, report_with_failure

# The evidence a blocked precondition carries; the refusal must reproduce it verbatim so an
# operator reads why, not merely that torque was refused.
BLOCK_DETAIL = "link state unread; ip -details link show could not be parsed"

# A pose one joint wider than the spatula build carries — what a bus that polled the absent
# gripper id would hand back.
EXTRA_JOINT_ANGLE_RAD = 0.99

# Modules the default stop-path scan must actually have read. A root repointed away from the
# package would report clean over nothing, and these names are what make that visible.
SCANNED_MODULE_NAMES = ("sequence.py", "stop_path.py", "estop.py")


class _BareMountTool(ToolDefinition):
    """A registered-shape tool that puts no motor on the bus at all.

    Not in `TOOL_REGISTRY`: every row there carries the seven arm joints, so a zero-motor
    build cannot be reached from the registry and the refusal for one needs a tool defined
    here to fire against.
    """

    @property
    def motor_send_ids(self) -> tuple[int, ...]:
        """No CAN send ids: nothing on this arm answers."""
        return ()


class _FailingAfterEnableBus(RecordingEngageBus):
    """A bus whose 0xFC leaves and is then followed by a fault.

    The state it produces is the one the disengage exists for: torque may be live while the
    session's `engaged` is still false.
    """

    def enable_torque(self, send_ids, hold_batch) -> None:  # noqa: ANN001
        """Record the engage, then fault the way a bus does after the frame is already out."""
        super().enable_torque(send_ids, hold_batch)
        raise RuntimeError("bus fault after 0xFC left")


def _session(
    bus: RecordingEngageBus,
    profile: EndEffectorProfile,
    preflight: PreflightReport,
    manifest: TorqueOnManifest,
) -> GuardedTorqueOn:
    """Build a session over the four things a guarded torque-ON is bound to."""
    return GuardedTorqueOn(bus, profile, preflight, manifest)


# --- Refusal 1: a blocked preflight precondition, named ---


def test_engage_refused_when_a_preflight_precondition_fails(
    recording_bus: RecordingEngageBus,
    fitted_profile: EndEffectorProfile,
    passing_manifest: TorqueOnManifest,
) -> None:
    blocked = report_with_failure(PreflightCheck.CAN_FD_LINK, BLOCK_DETAIL)
    session = _session(recording_bus, fitted_profile, blocked, passing_manifest)
    with pytest.raises(TorqueOnBlockedError) as refusal:
        session.engage()
    # The refusal names the precondition and repeats its evidence.
    assert PreflightCheck.CAN_FD_LINK.value in str(refusal.value)
    assert BLOCK_DETAIL in str(refusal.value)
    # And it refused at the door: nothing was read and no 0xFC went out.
    assert recording_bus.calls == []
    assert not session.torque_may_be_live


def test_every_preflight_precondition_blocks_the_engage_on_its_own(
    recording_bus: RecordingEngageBus,
    fitted_profile: EndEffectorProfile,
    passing_manifest: TorqueOnManifest,
) -> None:
    # No precondition is decorative: each one alone is enough to refuse torque.
    for check in PreflightCheck:
        blocked = report_with_failure(check, BLOCK_DETAIL)
        session = _session(recording_bus, fitted_profile, blocked, passing_manifest)
        with pytest.raises(TorqueOnBlockedError) as refusal:
            session.engage()
        assert check.value in str(refusal.value)
    assert recording_bus.calls == []


# --- Refusal 2 / the positive property: only the fitted motors are addressed ---


def test_engage_addresses_only_the_fitted_motors(
    recording_bus: RecordingEngageBus,
    fitted_profile: EndEffectorProfile,
    passing_preflight: PreflightReport,
    passing_manifest: TorqueOnManifest,
) -> None:
    # The bench carries a fixed spatula: seven motors, and 0x08 is not on the bus. Every
    # call the engage makes addresses exactly that set.
    session = _session(recording_bus, fitted_profile, passing_preflight, passing_manifest)
    result = session.engage()
    assert result.send_ids == fitted_profile.motor_send_ids
    assert GRIPPER_SEND_ID not in result.send_ids
    assert len(result.hold_batch) == fitted_profile.motor_count
    for addressed in recording_bus.addressed_ids:
        assert addressed == fitted_profile.motor_send_ids


def test_engaged_motor_set_follows_the_fitted_tool(
    gripper_profile: EndEffectorProfile,
    passing_preflight: PreflightReport,
    passing_manifest: TorqueOnManifest,
) -> None:
    # Not a hardcoded seven either: a build that does carry 0x08 engages it. The set comes
    # from the tool, so neither number is written into the engage.
    bus = RecordingEngageBus(pose_for(gripper_profile))
    result = _session(bus, gripper_profile, passing_preflight, passing_manifest).engage()
    assert GRIPPER_SEND_ID in result.send_ids
    assert result.send_ids == gripper_profile.motor_send_ids


def test_engage_refused_when_the_read_covers_more_than_the_fitted_motors(
    fitted_profile: EndEffectorProfile,
    passing_preflight: PreflightReport,
    passing_manifest: TorqueOnManifest,
) -> None:
    # A bus that answers eight-wide on a seven-motor arm polled a motor that is not there.
    # Refused rather than trimmed: the frame already went out, and the next one must not.
    over_wide = (*pose_for(fitted_profile), Rad(EXTRA_JOINT_ANGLE_RAD))
    bus = RecordingEngageBus(over_wide)
    session = _session(bus, fitted_profile, passing_preflight, passing_manifest)
    with pytest.raises(FittedMotorMismatchError, match="ERROR-PASSIVE"):
        session.engage()
    assert "enable_torque" not in bus.calls
    assert not session.torque_may_be_live


def test_engage_refused_when_the_read_covers_fewer_than_the_fitted_motors(
    fitted_profile: EndEffectorProfile,
    passing_preflight: PreflightReport,
    passing_manifest: TorqueOnManifest,
) -> None:
    # The other half of the width refusal, and a different failure: a fitted joint went
    # unread, so 0xFC would energize it holding an angle nobody measured.
    under_wide = pose_for(fitted_profile)[:-1]
    bus = RecordingEngageBus(under_wide)
    session = _session(bus, fitted_profile, passing_preflight, passing_manifest)
    with pytest.raises(FittedMotorMismatchError, match="nobody read"):
        session.engage()
    assert "enable_torque" not in bus.calls
    assert not session.torque_may_be_live


def test_engage_refused_when_the_fitted_tool_declares_no_motors(
    passing_preflight: PreflightReport,
    passing_manifest: TorqueOnManifest,
) -> None:
    # A tool with no motors leaves nothing to engage, and the zero-width frame it would
    # produce is refused before the bus is touched rather than sent as an empty batch.
    bare = EndEffectorProfile(
        tool=_BareMountTool(tool_id="bare_mount", label="bare mount", gripper_motor=False),
        tool_mass_kg=None,
    )
    bus = RecordingEngageBus(())
    session = _session(bus, bare, passing_preflight, passing_manifest)
    with pytest.raises(FittedMotorMismatchError, match="declares no motors"):
        session.engage()
    assert bus.calls == []
    assert not session.torque_may_be_live


# --- Refusal 3: the stop path cuts no torque ---


def test_stop_path_scan_is_clean_over_this_package() -> None:
    assert find_torque_cut_on_stop_path() == ()


def test_default_scan_root_is_this_package() -> None:
    # The clean result above is a finding of absence only while the default root is this
    # package. Pointed anywhere with no Python in it, the same call reports clean over
    # nothing, and the engage's precondition becomes unfailable.
    package_dir = Path(sequence_module.__file__).resolve().parent
    assert package_dir == TORQUE_BRINGUP_ROOT
    scanned = {path.name for path in TORQUE_BRINGUP_ROOT.rglob("*.py")}
    assert set(SCANNED_MODULE_NAMES) <= scanned


def test_stop_path_scan_catches_a_planted_torque_cut(tmp_path) -> None:  # noqa: ANN001
    # The refusal is real, not a scanner that never fires: a planted torque cut is found
    # and turned into a raise.
    (tmp_path / "leak.py").write_text(
        "def stop(bus):\n    bus.disable_torque()\n", encoding="utf-8"
    )
    assert find_torque_cut_on_stop_path(tmp_path)
    with pytest.raises(TorqueCutOnStopPathError, match="no holding brake"):
        assert_stop_path_cuts_no_torque(tmp_path)


def test_engage_runs_the_stop_path_refusal_before_touching_the_bus(
    monkeypatch: pytest.MonkeyPatch,
    recording_bus: RecordingEngageBus,
    fitted_profile: EndEffectorProfile,
    passing_preflight: PreflightReport,
    passing_manifest: TorqueOnManifest,
) -> None:
    # The scan is wired into the engage, not merely available beside it: when it refuses,
    # no pose is read and no torque is enabled.
    def refuse(root: object = None) -> None:
        raise TorqueCutOnStopPathError("planted")

    monkeypatch.setattr(sequence_module, "assert_stop_path_cuts_no_torque", refuse)
    session = _session(recording_bus, fitted_profile, passing_preflight, passing_manifest)
    with pytest.raises(TorqueCutOnStopPathError):
        session.engage()
    assert recording_bus.calls == []


# --- Refusal 4: the disengage, and the arm's own weight ---


def test_disengage_refused_while_the_arm_is_unsupported(
    recording_bus: RecordingEngageBus,
    fitted_profile: EndEffectorProfile,
    passing_preflight: PreflightReport,
    passing_manifest: TorqueOnManifest,
) -> None:
    session = _session(recording_bus, fitted_profile, passing_preflight, passing_manifest)
    session.engage()
    with pytest.raises(TorqueDisengageRefusedError, match="holding brake"):
        session.disengage(arm_supported=False)
    # Torque is still on and the session still says so — a refused release changes nothing.
    assert "drop_torque" not in recording_bus.calls
    assert session.torque_may_be_live


def test_disengage_drops_torque_on_the_fitted_motors(
    recording_bus: RecordingEngageBus,
    fitted_profile: EndEffectorProfile,
    passing_preflight: PreflightReport,
    passing_manifest: TorqueOnManifest,
) -> None:
    session = _session(recording_bus, fitted_profile, passing_preflight, passing_manifest)
    session.engage()
    dropped = session.disengage(arm_supported=True)
    assert recording_bus.calls == ["read_present_pose", "enable_torque", "drop_torque"]
    assert dropped == fitted_profile.motor_send_ids
    assert GRIPPER_SEND_ID not in dropped
    # What the drop put on the wire, not only what it reported: an 0xFD to the absent 0x08
    # is an unanswered frame like any other, and the return value would not show it.
    assert recording_bus.addressed_ids[-1] == fitted_profile.motor_send_ids
    assert GRIPPER_SEND_ID not in recording_bus.addressed_ids[-1]
    assert not session.engaged
    assert not session.torque_may_be_live


def test_disengage_is_available_after_an_engage_that_raised(
    fitted_profile: EndEffectorProfile,
    passing_preflight: PreflightReport,
    passing_manifest: TorqueOnManifest,
) -> None:
    # A bus that raises after 0xFC leaves torque on with `engaged` false. Refusing the
    # release there would strand the operator holding a live arm.
    bus = _FailingAfterEnableBus(pose_for(fitted_profile))
    session = _session(bus, fitted_profile, passing_preflight, passing_manifest)
    with pytest.raises(RuntimeError, match="bus fault"):
        session.engage()
    assert not session.engaged
    assert session.torque_may_be_live
    session.disengage(arm_supported=True)
    assert bus.calls[-1] == "drop_torque"


def test_disengage_refused_unsupported_even_when_the_session_never_engaged(
    fitted_profile: EndEffectorProfile,
    passing_preflight: PreflightReport,
    passing_manifest: TorqueOnManifest,
) -> None:
    # The same state the previous test releases from — torque live, `engaged` false — is
    # the one the support refusal must still cover. Tying the refusal to `engaged` would
    # drop a live brakeless arm in exactly the case the disengage exists to serve.
    bus = _FailingAfterEnableBus(pose_for(fitted_profile))
    session = _session(bus, fitted_profile, passing_preflight, passing_manifest)
    with pytest.raises(RuntimeError, match="bus fault"):
        session.engage()
    assert not session.engaged
    assert session.torque_may_be_live
    with pytest.raises(TorqueDisengageRefusedError, match="holding brake"):
        session.disengage(arm_supported=False)
    assert "drop_torque" not in bus.calls
    assert session.torque_may_be_live
