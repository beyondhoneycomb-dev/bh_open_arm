"""The verdict is the judge's, and an inconclusive one stays inconclusive all the way to disk.

`judge` refuses a round where two channels moved, or where one moved while another drifted into
the band between the thresholds. Everything downstream of it here — the record, `--status`, and
the command that writes the binding — has to carry that refusal rather than resolve it, because
the answer this file would otherwise invent is the one that sends left-arm commands to the right
arm (`05` §3-2a).
"""

from __future__ import annotations

import io
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from backend.endeffector import SIDE_LEFT, SIDE_RIGHT
from ops.hw.canbind import (
    ArmRole,
    BindingError,
    ChannelMotion,
    IdentificationResult,
    binding_path,
    judge,
    load_binding,
)
from scripts import canbind_session as session
from scripts.canbind_session_tests.canbind_doubles import (
    INTERFACE_A,
    INTERFACE_B,
    channel_lister,
    two_channels,
)

# Two channels that both cleared the motion gate: a hand on each arm, or a knock down a cable.
BOTH_MOVED_RAD = 0.2

# Inside the band the thresholds leave empty on purpose (0.01 .. 0.05 rad) — not moved, not quiet.
MIDDLE_BAND_RAD = 0.03

# A clean move, and the stillness the other channel has to hold to make it an answer.
CLEAN_MOVE_RAD = 0.1
STILL_RAD = 0.0005


def _config(tmp_path: Path, side: str) -> session.SessionConfig:
    """A round config confined to a temporary tree."""
    return session.SessionConfig(side=side, captures_root=tmp_path)


def _binding_dir(tmp_path: Path) -> Path:
    """Where the binding record is written, kept out of the capture tree the rounds live in."""
    return tmp_path / "config"


def _record(tmp_path: Path, side: str, moved: str | None, others: dict[str, float]) -> None:
    """Judge one round from stated per-channel motion and record it the way the worker does."""
    motions = tuple(
        ChannelMotion(interface=interface, max_delta_rad=delta)
        for interface, delta in others.items()
    )
    result = judge(motions)
    assert result.moved_interface == moved
    session.record_round(_config(tmp_path, side), session.round_entry_from(result, two_channels()))


def _resolve(tmp_path: Path, side: str, moved: str) -> None:
    """Record a round that resolved onto one channel."""
    still = INTERFACE_B if moved == INTERFACE_A else INTERFACE_A
    _record(tmp_path, side, moved, {moved: CLEAN_MOVE_RAD, still: STILL_RAD})


def test_two_moved_channels_are_recorded_as_inconclusive(tmp_path: Path) -> None:
    """Both arms moving is "both arms moved", never the one that moved further."""
    _record(
        tmp_path,
        SIDE_LEFT,
        None,
        {INTERFACE_A: BOTH_MOVED_RAD, INTERFACE_B: BOTH_MOVED_RAD / 2},
    )

    entry = session.read_rounds(tmp_path)[SIDE_LEFT]

    assert entry[session.FIELD_STATE] == session.ROUND_INCONCLUSIVE
    assert entry[session.FIELD_MOVED_INTERFACE] is None
    assert entry[session.FIELD_MOVED_CHANNEL_KEY] is None
    assert INTERFACE_B in entry[session.FIELD_REASON]


def test_the_band_between_the_thresholds_is_recorded_as_inconclusive(tmp_path: Path) -> None:
    """One channel moved and the other did not hold still: the deliberate "ask again" band."""
    _record(
        tmp_path,
        SIDE_LEFT,
        None,
        {INTERFACE_A: CLEAN_MOVE_RAD, INTERFACE_B: MIDDLE_BAND_RAD},
    )

    entry = session.read_rounds(tmp_path)[SIDE_LEFT]

    assert entry[session.FIELD_STATE] == session.ROUND_INCONCLUSIVE


def test_status_reports_an_inconclusive_round_as_refused(tmp_path: Path) -> None:
    """Not-yet-answered is not answered, and the exit code is what a caller reads."""
    _record(
        tmp_path,
        SIDE_LEFT,
        None,
        {INTERFACE_A: BOTH_MOVED_RAD, INTERFACE_B: BOTH_MOVED_RAD},
    )
    _resolve(tmp_path, SIDE_RIGHT, INTERFACE_B)

    with redirect_stdout(io.StringIO()):
        code = session.report_status(tmp_path)

    assert code == session.EXIT_REFUSED


def test_an_inconclusive_round_writes_no_binding(tmp_path: Path) -> None:
    """The file that would be written is the one that makes the torque session's gate pass."""
    _record(
        tmp_path,
        SIDE_LEFT,
        None,
        {INTERFACE_A: BOTH_MOVED_RAD, INTERFACE_B: BOTH_MOVED_RAD},
    )
    _resolve(tmp_path, SIDE_RIGHT, INTERFACE_B)

    with redirect_stdout(io.StringIO()):
        code = session.write_binding(tmp_path, _binding_dir(tmp_path))

    assert code == session.EXIT_REFUSED
    assert not binding_path(_binding_dir(tmp_path)).exists()


def test_one_resolved_arm_is_not_a_finished_procedure(tmp_path: Path) -> None:
    """The record needs both roles; an arm with no round is "not finished", not "passed"."""
    _resolve(tmp_path, SIDE_LEFT, INTERFACE_A)

    with redirect_stdout(io.StringIO()):
        code = session.report_status(tmp_path)

    assert code == session.EXIT_RUNNING


def test_no_round_at_all_is_its_own_exit_code(tmp_path: Path) -> None:
    """ "Never started" and "not finished" want opposite responses, so they are separate codes."""
    with redirect_stdout(io.StringIO()):
        assert session.report_status(tmp_path) == session.EXIT_NO_SESSION


def test_two_rounds_landing_on_one_channel_are_refused(tmp_path: Path) -> None:
    """One socket cannot be two arms, and the binding file refuses it at read time anyway."""
    _resolve(tmp_path, SIDE_LEFT, INTERFACE_A)
    _resolve(tmp_path, SIDE_RIGHT, INTERFACE_A)

    with redirect_stdout(io.StringIO()):
        assert session.report_status(tmp_path) == session.EXIT_REFUSED
        assert session.write_binding(tmp_path, _binding_dir(tmp_path)) == session.EXIT_REFUSED

    assert not binding_path(_binding_dir(tmp_path)).exists()


def test_both_resolved_arms_are_written_through_the_canbind_record(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The answer is persisted in `ops.hw.canbind`'s own format, keyed on the stable channel key.

    Never on `canN`: the interface name is not stable across a re-plug, which is the whole reason
    the record exists.
    """
    _resolve(tmp_path, SIDE_LEFT, INTERFACE_A)
    _resolve(tmp_path, SIDE_RIGHT, INTERFACE_B)
    channels = two_channels()
    monkeypatch.setattr(session, "list_can_channels", channel_lister(channels))

    with redirect_stdout(io.StringIO()):
        code = session.write_binding(tmp_path, _binding_dir(tmp_path))

    assert code == session.EXIT_OK
    stored = load_binding(binding_path(_binding_dir(tmp_path)))
    assert stored.key_for(ArmRole.FOLLOWER_LEFT) == channels[0].channel_key
    assert stored.key_for(ArmRole.FOLLOWER_RIGHT) == channels[1].channel_key
    assert stored.interface_for(ArmRole.FOLLOWER_LEFT, channels) == INTERFACE_A


def test_a_binding_is_not_written_for_channels_that_have_since_gone(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An adapter that moved ports between the round and the write invalidates the round.

    Writing the old answer against the new enumeration is exactly the act `05` §3-2a records
    happening on this bench: the gate passes and not one character of it is an identification.
    """
    _resolve(tmp_path, SIDE_LEFT, INTERFACE_A)
    _resolve(tmp_path, SIDE_RIGHT, INTERFACE_B)
    monkeypatch.setattr(session, "list_can_channels", channel_lister(()))

    with redirect_stdout(io.StringIO()):
        code = session.write_binding(tmp_path, _binding_dir(tmp_path))

    assert code == session.EXIT_REFUSED
    with pytest.raises(BindingError):
        load_binding(binding_path(_binding_dir(tmp_path)))


def test_the_role_names_written_are_the_ones_the_rig_reads_back() -> None:
    """A disagreement here files the left arm's answer under the right arm's name.

    `scripts.rig_session` resolves an arm to a channel through its own side-to-role map. The two
    maps are separate because the producer must not import the consumer — this program determines
    the binding that consumer reads — so their agreement is asserted instead of assumed.
    """
    from scripts.rig_session import ARM_ROLE_BY_SIDE

    assert session.ROLE_BY_SIDE == ARM_ROLE_BY_SIDE


def test_the_recorded_numbers_are_the_ones_the_judge_saw() -> None:
    """The operator is shown the deltas, not just the verdict; a bare verdict cannot be argued."""
    result = IdentificationResult(
        moved_interface=INTERFACE_A,
        motions=(
            ChannelMotion(interface=INTERFACE_A, max_delta_rad=CLEAN_MOVE_RAD),
            ChannelMotion(interface=INTERFACE_B, max_delta_rad=STILL_RAD),
        ),
        reason="",
    )

    entry = session.round_entry_from(result, two_channels())

    assert entry[session.FIELD_MOTIONS] == [
        {session.FIELD_INTERFACE: INTERFACE_A, session.FIELD_MAX_DELTA_RAD: CLEAN_MOVE_RAD},
        {session.FIELD_INTERFACE: INTERFACE_B, session.FIELD_MAX_DELTA_RAD: STILL_RAD},
    ]
    assert entry[session.FIELD_MOVED_CHANNEL_KEY] == two_channels()[0].channel_key
