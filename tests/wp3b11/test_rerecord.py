"""Acceptance ③/④: a re-record clears the buffer and does not advance the index.

A re-record must discard the running episode without saving it, so the episode
index the next saved episode gets is the one the discarded episode would have had —
nothing counts a re-record. The control flow is checked against a fake dataset
(one clear, no extra save), and the outcome against a real `LeRobotDataset`: after
one re-record and two saved episodes the recorded `episode_index` values are a
contiguous `{0, 1}`, and the discarded frames left no row behind.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import backend.recorder.embed.session as session_mod
from backend.recorder.embed import RecordEvents, RecordSpec, record_session

from ._support import DummyRobotAdapter, FakeDataset, RampTeleop, RerecordOnceTeleop

FPS = 30
EPISODE_STEPS = 4


def _spec(num_episodes: int) -> RecordSpec:
    """A session spec with a fixed per-episode frame budget."""
    return RecordSpec(
        repo_id="synthetic/rerecord",
        single_task="grab",
        fps=FPS,
        bimanual=True,
        use_velocity_and_torque=True,
        num_episodes=num_episodes,
        episode_steps=EPISODE_STEPS,
        reset_steps=2,
    )


def _episode_index_values(root: Path) -> list[int]:
    """Read the recorded per-frame `episode_index` values from the data parquet."""
    frames = pd.concat(pd.read_parquet(path) for path in sorted(root.glob("data/**/*.parquet")))
    return sorted(frames["episode_index"].unique().tolist())


def test_rerecord_clears_without_saving(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A re-recorded episode is cleared once and never saved; two survive."""
    fake = FakeDataset(fps=FPS)
    monkeypatch.setattr(
        session_mod, "create_record_dataset", lambda *_a, **_k: (fake, "synthetic/rerecord_stamped")
    )
    events = RecordEvents()
    teleop = RerecordOnceTeleop(bimanual=True, events=events, fire_after=2)
    result = record_session(_spec(2), DummyRobotAdapter(True, True), teleop, events, tmp_path)

    assert result.rerecorded_episodes == 1
    assert result.saved_episodes == 2
    assert fake.clear_calls == 1
    assert fake.save_calls == 2
    # The two saved episodes are the full-length passes, not the discarded partial one.
    assert fake.saved_episode_sizes == [EPISODE_STEPS, EPISODE_STEPS]


def test_rerecord_does_not_advance_episode_index(tmp_path: Path) -> None:
    """On a real dataset the saved indices are a contiguous {0, 1} after one re-record."""
    root = tmp_path / "ds"
    events = RecordEvents()
    teleop = RerecordOnceTeleop(bimanual=True, events=events, fire_after=2)
    result = record_session(_spec(2), DummyRobotAdapter(True, True), teleop, events, root)

    assert result.rerecorded_episodes == 1
    assert result.saved_episodes == 2
    assert _episode_index_values(root) == [0, 1]


def test_a_clean_session_indexes_from_zero(tmp_path: Path) -> None:
    """Without a re-record the same two episodes still index 0 and 1 (no drift)."""
    root = tmp_path / "ds"
    events = RecordEvents()
    result = record_session(_spec(2), DummyRobotAdapter(True, True), RampTeleop(True), events, root)

    assert result.rerecorded_episodes == 0
    assert result.saved_episodes == 2
    assert _episode_index_values(root) == [0, 1]
