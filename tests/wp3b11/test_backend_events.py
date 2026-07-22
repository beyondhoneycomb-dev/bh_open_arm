"""Acceptance ②: the events dict is backend-owned, not driven by a key listener.

Two halves: statically, the embed imports no `pynput` hook, no controlling-TTY
reader, and no LeRobot keyboard backend, and calls the listener factory nowhere
(so nothing but the backend can set the flags). Behaviourally, `RecordEvents`
carries exactly LeRobot's three keys and the command surface sets them the way a
keypress would, so `record_loop` cannot tell a button from a key.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.recorder.embed import (
    EVENT_KEYS,
    EXIT_EARLY_KEY,
    RERECORD_EPISODE_KEY,
    STOP_RECORDING_KEY,
    RecordEvents,
    scan_source,
)

LISTENER_VIOLATIONS = [
    "from pynput import keyboard\n",
    "import pynput\n",
    "import termios\n",
    "import tty\n",
    "from lerobot.utils.keyboard_input import init_keyboard_listener\n",
    "listener, events = init_keyboard_listener()\n",
    "from lerobot.utils.keyboard_input import TerminalKeyListener\n",
]


@pytest.mark.parametrize("source", LISTENER_VIOLATIONS)
def test_scan_bites_on_a_key_listener(source: str) -> None:
    """Every pynput/TTY/keyboard-backend fixture is caught."""
    assert scan_source(Path("violation.py"), source)


def test_events_carry_lerobots_three_keys() -> None:
    """The events dict is exactly LeRobot's `exit_early`/`rerecord_episode`/`stop_recording`."""
    keys = set(RecordEvents().as_dict())
    assert keys == {EXIT_EARLY_KEY, RERECORD_EPISODE_KEY, STOP_RECORDING_KEY}
    assert set(EVENT_KEYS) == keys


def test_fresh_events_end_no_episode() -> None:
    """A new session's flags are all clear — nothing ends an episode by default."""
    events = RecordEvents()
    assert not events.take_exit_early()
    assert not events.mRerecordEpisode
    assert not events.mStopRecording


def test_end_episode_command_sets_only_exit_early() -> None:
    """Ending an episode raises exit-early alone, keeping the episode."""
    events = RecordEvents()
    events.request_end_episode()
    assert events.as_dict() == {
        EXIT_EARLY_KEY: True,
        RERECORD_EPISODE_KEY: False,
        STOP_RECORDING_KEY: False,
    }


def test_rerecord_command_also_ends_the_episode() -> None:
    """A re-record request ends the running episode too — the keypress coupling."""
    events = RecordEvents()
    events.request_rerecord()
    assert events.mRerecordEpisode
    assert events.mExitEarly


def test_stop_command_also_ends_the_episode() -> None:
    """A stop request ends the running episode too."""
    events = RecordEvents()
    events.request_stop()
    assert events.mStopRecording
    assert events.mExitEarly


def test_take_exit_early_reads_and_clears() -> None:
    """Early-exit is consumed once, so the loop cannot spin on a latched flag."""
    events = RecordEvents()
    events.request_end_episode()
    assert events.take_exit_early()
    assert not events.take_exit_early()
