"""WP-3C-07 ④/⑤: the journal restores the session, and the resume never re-stamps.

`02b` §7 WP-3C-07 ④: a journal restores the stamped `repo_id`, task, episode counter and
config. ⑤: on resume `stamp_repo_id()` is not called — the existing stamped id is carried
through unchanged, because re-stamping mints a divergent name and orphans the crashed
session's data.

The ⑤ proof has three legs: the restored id equals the recorder's original id verbatim;
a spy on the recorder's real `stamp_repo_id` records zero calls across the whole resume;
and — so the tripwire is not vacuous — the recorder's real `stamp_repo_id`, applied a
second time, is shown to produce the doubled-stamp id `has_double_stamp` catches.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import backend.recorder.embed.dataset as recorder_dataset
from backend.crash_recovery.journal import (
    has_double_stamp,
    read_journal,
    restore_session,
    write_journal,
)
from backend.recorder.embed import stamp_repo_id
from tests.wp3c07.support import TASK, build_baseline_dataset, make_journal

_SAVED_EPISODES = 2
_SESSION_TARGET = 4


def _prepare(root: Path) -> str:
    """Record a baseline, journal it, and return the recorder's stamped id."""
    result = build_baseline_dataset(root, _SAVED_EPISODES)
    write_journal(root, make_journal(result, _SESSION_TARGET))
    return result.repo_id


def test_journal_round_trips(tmp_path: Path) -> None:
    """A written journal reads back identically — the crash-surviving record is intact."""
    root = tmp_path / "ds"
    stamped = _prepare(root)

    journal = read_journal(root)

    assert journal.stamped_repo_id == stamped
    assert journal.single_task == TASK
    assert journal.saved_episodes == _SAVED_EPISODES
    assert journal.num_episodes == _SESSION_TARGET


def test_restore_recovers_stamped_id_task_counter_and_config(tmp_path: Path) -> None:
    """④ The resume plan restores the stamped id, task, episode counter and config."""
    root = tmp_path / "ds"
    stamped = _prepare(root)

    plan = restore_session(root)

    assert plan.stamped_repo_id == stamped
    assert plan.single_task == TASK
    assert plan.next_episode_index == _SAVED_EPISODES
    assert plan.remaining_episodes == _SESSION_TARGET - _SAVED_EPISODES
    assert plan.fps > 0
    assert plan.bimanual is False
    assert plan.use_velocity_and_torque is False


def test_resume_carries_the_existing_id_verbatim(tmp_path: Path) -> None:
    """⑤ The restored id is the original, singly-stamped — not re-derived."""
    root = tmp_path / "ds"
    stamped = _prepare(root)

    plan = restore_session(root)

    assert plan.stamped_repo_id == stamped
    assert has_double_stamp(plan.stamped_repo_id) is False


def test_resume_never_calls_stamp_repo_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """⑤ A spy on the recorder's real `stamp_repo_id` records zero calls during resume."""
    root = tmp_path / "ds"
    _prepare(root)

    calls: list[str] = []
    real_stamp = recorder_dataset.stamp_repo_id

    def _spy(repo_id: str, moment: object = None) -> str:
        calls.append(repo_id)
        return real_stamp(repo_id, moment)  # type: ignore[arg-type]

    monkeypatch.setattr(recorder_dataset, "stamp_repo_id", _spy)

    plan = restore_session(root)

    assert calls == []
    assert has_double_stamp(plan.stamped_repo_id) is False


def test_double_stamp_tripwire_is_not_vacuous() -> None:
    """A second real `stamp_repo_id` produces the divergent doubled id the tripwire catches."""
    once = stamp_repo_id("synthetic/drill")
    twice = stamp_repo_id(once)

    assert has_double_stamp(once) is False
    assert twice != once
    assert has_double_stamp(twice) is True
