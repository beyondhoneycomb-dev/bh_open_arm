"""The backend-owned episode-control events for the recorder embed (WP-3B-11).

LeRobot's `record_loop()` reads episode control — end this episode, re-record it,
stop the session — from an `events` dict that `init_keyboard_listener()` fills
from a `pynput` global hook or a controlling-TTY reader (`utils/keyboard_input.py`).
A headless robot backend has no keyboard to own that dict; the GUI/WS command
layer does. `RecordEvents` is that ownership: a plain flag container the backend
mutates from commands, exposing the *same* three keys `record_loop()` subscripts,
with no key listener behind it. That absence is the whole point (WP-3B-11
acceptance ②) — the events are driven by S-07's start/re-record/stop buttons
(`FR-GUI-102`), never by a captured keypress.
"""

from __future__ import annotations

from backend.recorder.embed.constants import (
    EXIT_EARLY_KEY,
    RERECORD_EPISODE_KEY,
    STOP_RECORDING_KEY,
)


class RecordEvents:
    """Backend-owned episode-control flags, set by commands and read by the loop.

    The three flags mirror LeRobot's `events` dict exactly. The command methods are
    the backend's write surface (a WS/GUI handler calls them); the loop and the
    session are the read surface. `request_rerecord` and `request_stop` also raise
    the early-exit flag, because both first have to end the running episode — the
    same coupling `apply_recording_control` gives the keyboard backend, kept here so
    a command drives the loop identically to a keypress.
    """

    def __init__(self) -> None:
        """Start with every flag cleared — a fresh session ends no episode."""
        self.mExitEarly = False
        self.mRerecordEpisode = False
        self.mStopRecording = False

    def request_end_episode(self) -> None:
        """End the current episode early, keeping it (a normal episode boundary)."""
        self.mExitEarly = True

    def request_rerecord(self) -> None:
        """Discard and re-record the current episode: end it early, mark it re-record."""
        self.mRerecordEpisode = True
        self.mExitEarly = True

    def request_stop(self) -> None:
        """Stop the whole session: end the current episode early, mark stop."""
        self.mStopRecording = True
        self.mExitEarly = True

    def take_exit_early(self) -> bool:
        """Return whether an early exit is pending and clear it.

        The read-and-clear is one step so the loop cannot spin on a latched flag —
        it is exactly `record_loop`'s `if events["exit_early"]: events["exit_early"]
        = False; break`.

        Returns:
            (bool) True when an early exit was pending.
        """
        pending = self.mExitEarly
        self.mExitEarly = False
        return pending

    def as_dict(self) -> dict[str, bool]:
        """Render the LeRobot-shaped events dict, for a call site that wants the dict.

        Returns:
            (dict[str, bool]) The three flags under LeRobot's own key names.
        """
        return {
            EXIT_EARLY_KEY: self.mExitEarly,
            RERECORD_EPISODE_KEY: self.mRerecordEpisode,
            STOP_RECORDING_KEY: self.mStopRecording,
        }
