"""Dynamic CAN channel identity — the mechanism that replaces udev renaming on this rig.

The property under test is not "the code runs" but "the code refuses to guess". Both arms are
indistinguishable on the bus (`03` §2.1) and this rig's adapter reports no serial, so every
shortcut — take the first CAN interface, take the lower `dev_id`, take the larger motion —
produces an answer that looks correct until an arm moves against the other arm's limits. Each
of those shortcuts is planted here and must be rejected.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ops.hw.canbind import (
    MOTION_THRESHOLD_RAD,
    QUIET_THRESHOLD_RAD,
    ArmRole,
    BindingError,
    CanChannel,
    ChannelBinding,
    binding_path,
    bring_up_command,
    check_binding,
    identify_moved_channel,
    judge,
    list_can_channels,
    load_binding,
    measure_motion,
    read_baseline,
    save_binding,
)
from ops.hw.canbind.identify import ChannelMotion, IdentificationError

# The two channels of one PCAN-USB Pro FD as this bench actually reports them: one shared
# ID_PATH, distinct dev_id, no serial anywhere.
_PATH = "pci-0000:80:14.0-usb-0:10.3.1.2:1.0"
_CH0 = CanChannel(
    interface="can0",
    id_path=_PATH,
    dev_id="0x0",
    driver="peak_usb",
    state="ERROR-ACTIVE",
    bitrate_bps=1_000_000,
)
_CH1 = CanChannel(
    interface="can1",
    id_path=_PATH,
    dev_id="0x1",
    driver="peak_usb",
    state="ERROR-ACTIVE",
    bitrate_bps=1_000_000,
)


def _write_iface(root: Path, name: str, *, dev_id: str, is_can: bool = True) -> None:
    """Write a fake `/sys/class/net/<name>` tree."""
    entry = root / name
    entry.mkdir(parents=True)
    if is_can:
        (entry / "can_bittiming_const").mkdir()
        (entry / "can_bittiming").mkdir()
        (entry / "can_bittiming" / "bitrate").write_text("1000000\n", encoding="utf-8")
        (entry / "can_state").write_text("ERROR-ACTIVE\n", encoding="utf-8")
    (entry / "dev_id").write_text(f"{dev_id}\n", encoding="utf-8")


# ── discovery ────────────────────────────────────────────────────────────────────────────


def test_two_channels_of_one_adapter_do_not_collapse_to_one_key() -> None:
    """The whole reason `dev_id` is in the key: `ID_PATH` alone is identical for both."""
    assert _CH0.id_path == _CH1.id_path
    assert _CH0.channel_key != _CH1.channel_key


def test_a_missing_axis_becomes_an_explicit_marker_not_an_empty_string() -> None:
    """Two channels that each fail to report `dev_id` must not read as the same channel."""
    blank = CanChannel("can0", "", "", "", "", None)
    other = CanChannel("can1", "", "", "", "", None)

    assert "?" in blank.channel_key
    assert blank.channel_key == other.channel_key, (
        "identical unknowns do collide — which is why check_binding must surface it rather "
        "than the key pretending to be unique"
    )


def test_only_can_interfaces_are_enumerated(tmp_path: Path) -> None:
    """Keys on the CAN core's bittiming directory, not on a name prefix."""
    _write_iface(tmp_path, "can0", dev_id="0x0")
    _write_iface(tmp_path, "eth0", dev_id="0x0", is_can=False)
    _write_iface(tmp_path, "can_backup", dev_id="0x0", is_can=False)

    found = list_can_channels(tmp_path)

    assert [channel.interface for channel in found] == ["can0"]


def test_an_absent_sys_class_net_yields_no_channels(tmp_path: Path) -> None:
    """A host with no CAN adapter reports nothing rather than raising."""
    assert list_can_channels(tmp_path / "missing") == []


def test_bring_up_is_returned_as_a_command_never_executed() -> None:
    """Bring-up needs CAP_NET_ADMIN; a tool that escalates silently cannot be audited."""
    argv = bring_up_command("can0", 1_000_000, 5_000_000)

    assert argv[:2] == ["sudo", "ip"]
    assert "1000000" in argv
    assert "5000000" in argv
    assert argv[-2:] == ["fd", "on"]


# ── identification ───────────────────────────────────────────────────────────────────────


def test_the_channel_whose_joints_moved_is_the_answer() -> None:
    """The core substitution for udev: the arm identifies itself by moving."""
    result = judge(
        (
            ChannelMotion("can0", MOTION_THRESHOLD_RAD * 2),
            ChannelMotion("can1", 0.0),
        )
    )

    assert result.resolved
    assert result.moved_interface == "can0"


def test_two_channels_moving_is_refused_not_resolved_to_the_larger() -> None:
    """Picking the bigger number here is exactly how the arms get swapped."""
    result = judge(
        (
            ChannelMotion("can0", MOTION_THRESHOLD_RAD * 3),
            ChannelMotion("can1", MOTION_THRESHOLD_RAD * 2),
        )
    )

    assert not result.resolved
    assert "more than one channel moved" in result.reason


def test_nothing_moving_is_refused_with_the_things_to_check() -> None:
    """A still bus is unpowered, un-upped, or the operator did not move far enough."""
    result = judge((ChannelMotion("can0", 0.0), ChannelMotion("can1", 0.0)))

    assert not result.resolved
    assert "no channel moved" in result.reason


def test_a_drift_in_the_middle_band_is_refused() -> None:
    """The gap between the two thresholds is deliberately "ask again", not "close enough"."""
    drift = (MOTION_THRESHOLD_RAD + QUIET_THRESHOLD_RAD) / 2.0
    assert QUIET_THRESHOLD_RAD < drift < MOTION_THRESHOLD_RAD

    result = judge(
        (
            ChannelMotion("can0", MOTION_THRESHOLD_RAD * 2),
            ChannelMotion("can1", drift),
        )
    )

    assert not result.resolved
    assert "did not stay still" in result.reason


def test_no_channels_read_is_refused() -> None:
    """An empty round must not resolve to anything."""
    assert not judge(()).resolved


def test_a_changed_joint_width_between_readings_raises() -> None:
    """Comparing a 7-vector to an 8-vector would compute a delta over a truncation."""
    with pytest.raises(IdentificationError, match="joints"):
        measure_motion(("can0",), lambda _iface: (0.0,) * 7, {"can0": (0.0,) * 8})


def test_a_channel_without_a_baseline_raises() -> None:
    """Silently treating a missing baseline as zero would make any reading look like motion."""
    with pytest.raises(IdentificationError, match="baseline"):
        measure_motion(("can1",), lambda _iface: (0.0,) * 8, {"can0": (0.0,) * 8})


def test_one_full_round_reads_prompts_then_reads_again() -> None:
    """The prompt must land between the two readings, or the motion is never captured."""
    calls: list[str] = []
    positions = {"can0": [0.0] * 8, "can1": [0.0] * 8}

    def read(iface: str) -> list[float]:
        calls.append(f"read:{iface}")
        return list(positions[iface])

    def prompt() -> None:
        calls.append("prompt")
        positions["can1"][3] = MOTION_THRESHOLD_RAD * 2

    result = identify_moved_channel(("can0", "can1"), read, prompt)

    assert result.moved_interface == "can1"
    assert calls.index("prompt") == 2, calls


# ── binding ──────────────────────────────────────────────────────────────────────────────


def test_a_bound_role_resolves_to_whatever_the_kernel_calls_it_now() -> None:
    """The point of keying on the channel: `canN` may renumber and the answer still holds."""
    binding = ChannelBinding({ArmRole.FOLLOWER_LEFT: _CH1.channel_key})
    renumbered = CanChannel("can7", _PATH, "0x1", "peak_usb", "ERROR-ACTIVE", 1_000_000)

    assert binding.interface_for(ArmRole.FOLLOWER_LEFT, (renumbered,)) == "can7"


def test_an_unbound_role_is_refused_not_defaulted_to_the_only_channel() -> None:
    """ "There is only one CAN interface, it must be that one" is the shortcut that bites."""
    binding = ChannelBinding({})

    with pytest.raises(BindingError, match="no bound channel"):
        binding.interface_for(ArmRole.FOLLOWER_LEFT, (_CH0,))


def test_a_moved_adapter_is_refused_rather_than_rebound() -> None:
    """Observed on this bench: the same adapter appeared at 3-4:1.0 and later 3-10.3.1.2:1.0."""
    binding = ChannelBinding({ArmRole.FOLLOWER_LEFT: "pci-0000:80:14.0-usb-0:4:1.0/dev_id:0x0"})

    with pytest.raises(BindingError, match="not present now"):
        binding.interface_for(ArmRole.FOLLOWER_LEFT, (_CH0, _CH1))


def test_check_binding_reports_missing_and_unclaimed_separately() -> None:
    """An unclaimed channel is information; a missing one is a refusal. They are not the same."""
    binding = ChannelBinding({ArmRole.FOLLOWER_LEFT: _CH0.channel_key, ArmRole.LEADER_LEFT: "gone"})

    check = check_binding(binding, (_CH0, _CH1))

    assert check.resolved == {ArmRole.FOLLOWER_LEFT: "can0"}
    assert check.missing == (ArmRole.LEADER_LEFT,)
    assert check.unbound_keys == (_CH1.channel_key,)
    assert not check.ok


def test_a_binding_survives_a_save_and_load_round_trip(tmp_path: Path) -> None:
    """What is written must be what comes back; a role map is not a place for a lossy format."""
    original = ChannelBinding(
        {ArmRole.FOLLOWER_LEFT: _CH0.channel_key, ArmRole.FOLLOWER_RIGHT: _CH1.channel_key}
    )
    path = binding_path(tmp_path)

    save_binding(path, original)

    assert load_binding(path).roles == original.roles


def test_two_roles_claiming_one_channel_is_refused_at_read_time(tmp_path: Path) -> None:
    """One socket cannot be two arms; catching it at read beats catching it at first motion."""
    path = binding_path(tmp_path)
    path.write_text(
        '{"version": 1, "roles": {"follower_left": "k", "follower_right": "k"}}',
        encoding="utf-8",
    )

    with pytest.raises(BindingError, match="both claim"):
        load_binding(path)


def test_an_unknown_role_name_is_refused(tmp_path: Path) -> None:
    """A typo'd role must not be dropped silently, leaving that arm unbound and undetected."""
    path = binding_path(tmp_path)
    path.write_text('{"version": 1, "roles": {"folower_left": "k"}}', encoding="utf-8")

    with pytest.raises(BindingError, match="unknown role"):
        load_binding(path)


def test_a_version_mismatch_is_refused(tmp_path: Path) -> None:
    """A future format read as this one would bind arms from fields that moved."""
    path = binding_path(tmp_path)
    path.write_text('{"version": 99, "roles": {}}', encoding="utf-8")

    with pytest.raises(BindingError, match="version"):
        load_binding(path)


def test_a_malformed_file_is_refused(tmp_path: Path) -> None:
    """Refusing beats defaulting: an unreadable map means nobody knows which arm is which."""
    path = binding_path(tmp_path)
    path.write_text("not json at all", encoding="utf-8")

    with pytest.raises(BindingError):
        load_binding(path)


def test_a_failed_write_leaves_no_stray_temp_file(tmp_path: Path) -> None:
    """A leftover temp file is a second binding a later glob could pick up."""
    path = binding_path(tmp_path)
    save_binding(path, ChannelBinding({ArmRole.FOLLOWER_LEFT: _CH0.channel_key}))

    assert [p.name for p in tmp_path.iterdir()] == [path.name]


def test_read_baseline_snapshots_every_interface() -> None:
    """A baseline that shares mutable state with the reader would compare a list to itself."""
    live = [0.0] * 8

    baseline = read_baseline(("can0",), lambda _iface: live)
    live[0] = 1.0

    assert baseline["can0"][0] == 0.0
