"""Acceptance ④ single-arm mode, and ⑤ full inputSources[*].profiles logging."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from backend.teleop.webxr.profiles import ResolvedVia
from backend.teleop.webxr.session import Handedness, SessionError, TeleopMode
from tests.wp3b08.support import UNKNOWN_QUEST_PROFILE, input_source, session


def test_right_only_mode_begins_with_one_source(tmp_path: Path) -> None:
    # ④: a single right controller begins a RIGHT session — the upstream
    # inputSources.length < 2 drop is relaxed.
    sess = session(TeleopMode.RIGHT, tmp_path)
    sess.begin([input_source(Handedness.RIGHT)])
    assert sess.is_active
    assert sess.resolution_for(Handedness.RIGHT).via is ResolvedVia.XR_STANDARD


def test_left_only_mode_begins_with_one_source(tmp_path: Path) -> None:
    sess = session(TeleopMode.LEFT, tmp_path)
    sess.begin([input_source(Handedness.LEFT)])
    assert sess.is_active
    with pytest.raises(SessionError):
        sess.resolution_for(Handedness.RIGHT)  # right is not an active arm


def test_bimanual_mode_requires_both_arms(tmp_path: Path) -> None:
    sess = session(TeleopMode.BIMANUAL, tmp_path)
    with pytest.raises(SessionError):
        sess.begin([input_source(Handedness.RIGHT)])  # left missing
    assert not sess.is_active
    sess.begin([input_source(Handedness.LEFT), input_source(Handedness.RIGHT)])
    assert sess.is_active


def test_single_arm_mode_ignores_the_inactive_arm(tmp_path: Path) -> None:
    # A right-only session begins even when a left source is also present; only the
    # active arm is resolved.
    sess = session(TeleopMode.RIGHT, tmp_path)
    sess.begin([input_source(Handedness.RIGHT), input_source(Handedness.LEFT)])
    assert sess.is_active
    assert set(sess.logged_profiles) == {Handedness.RIGHT, Handedness.LEFT}
    assert Handedness.RIGHT in sess.logged_profiles


def test_active_sides_match_mode() -> None:
    assert TeleopMode.RIGHT.active_sides == (Handedness.RIGHT,)
    assert TeleopMode.LEFT.active_sides == (Handedness.LEFT,)
    assert TeleopMode.BIMANUAL.active_sides == (Handedness.LEFT, Handedness.RIGHT)
    assert TeleopMode.RIGHT.is_single_arm
    assert not TeleopMode.BIMANUAL.is_single_arm


def test_duplicate_arm_source_is_rejected(tmp_path: Path) -> None:
    sess = session(TeleopMode.RIGHT, tmp_path)
    with pytest.raises(SessionError):
        sess.begin([input_source(Handedness.RIGHT), input_source(Handedness.RIGHT)])


def test_begin_logs_full_profiles_of_every_source(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # ⑤: the full profiles array of every source is logged at begin — the only way to
    # confirm the fallback chain against a real Quest 3S (its strings are unconfirmed).
    profiles = [UNKNOWN_QUEST_PROFILE, "generic-trigger-squeeze-thumbstick"]
    sess = session(TeleopMode.BIMANUAL, tmp_path)
    with caplog.at_level(logging.INFO, logger="backend.teleop.webxr.session"):
        sess.begin(
            [
                input_source(Handedness.LEFT, profiles=profiles),
                input_source(Handedness.RIGHT, profiles=profiles),
            ]
        )
    assert sess.logged_profiles[Handedness.LEFT] == tuple(profiles)
    assert sess.logged_profiles[Handedness.RIGHT] == tuple(profiles)
    logged_text = " ".join(record.getMessage() for record in caplog.records)
    assert UNKNOWN_QUEST_PROFILE in logged_text
    assert "generic-trigger-squeeze-thumbstick" in logged_text


def test_begin_is_idempotent_on_reentry(tmp_path: Path) -> None:
    # Re-begin clears prior state rather than accumulating it.
    sess = session(TeleopMode.RIGHT, tmp_path)
    sess.begin([input_source(Handedness.RIGHT)])
    sess.begin([input_source(Handedness.RIGHT)])
    assert set(sess.logged_profiles) == {Handedness.RIGHT}


def test_resolution_before_begin_is_rejected(tmp_path: Path) -> None:
    sess = session(TeleopMode.RIGHT, tmp_path)
    with pytest.raises(SessionError):
        sess.resolution_for(Handedness.RIGHT)
