"""WP-3B-12 ⑤ — a footerless parquet is detected, isolated, recovery-attempted, then judged.

`02b` §5.2 WP-3B-12 ⑤: crash detection on a footerless parquet, isolation, a recovery
attempt, and a USER judgment with zero auto-saves. The recovery attempt reports honestly
whether a table read back; it never fabricates a reconstructed episode.
"""

from __future__ import annotations

from pathlib import Path

from backend.recorder.quality.crash import (
    attempt_recovery,
    is_footerless_parquet,
    recover,
)
from backend.recorder.quality.label import EpisodeStatus, Verdict
from backend.recorder.quality.sidecar import read_sidecar
from backend.recorder.quality.store import DatasetStore
from tests.wp3b12.support import write_footerless_parquet, write_valid_parquet


def test_valid_parquet_is_not_footerless(tmp_path: Path) -> None:
    """A complete parquet ending in the PAR1 magic is not flagged as a crash artefact."""
    path = write_valid_parquet(tmp_path / "data" / "episode_000000.parquet")
    assert is_footerless_parquet(path) is False


def test_footerless_parquet_is_detected(tmp_path: Path) -> None:
    """⑤ A parquet truncated before its footer is detected as footerless."""
    path = write_footerless_parquet(tmp_path / "data" / "episode_000000.parquet")
    assert is_footerless_parquet(path) is True


def test_missing_file_reads_as_footerless(tmp_path: Path) -> None:
    """A file that never appeared is treated as a crash artefact, not silently ignored."""
    assert is_footerless_parquet(tmp_path / "nope.parquet") is True


def test_recovery_isolates_attempts_and_requires_user_judgment(tmp_path: Path) -> None:
    """⑤ The full path: isolate -> attempt recover -> pending human judgment, zero auto-save."""
    store = DatasetStore(root=tmp_path)
    data_path = write_footerless_parquet(tmp_path / "data" / "episode_000003.parquet")

    outcome, label = recover(store, data_path, episode_index=3)

    # Isolated: the file left the data tree for quarantine.
    assert not data_path.exists()
    assert Path(outcome.quarantine_path).is_file()
    assert Path(outcome.quarantine_path).is_relative_to(store.quarantine_dir())
    # Recovery attempted and reported honestly: a footerless file yields no table.
    assert outcome.recovered is False
    assert outcome.salvaged_bytes > 0
    # User judgment required, and nothing auto-saved.
    assert outcome.requires_user_judgment is True
    assert outcome.auto_saved is False
    assert label.status is EpisodeStatus.PENDING_JUDGMENT
    assert label.requires_user_judgment() is True
    assert label.auto_saved is False
    # The pending judgment is persisted as a sidecar for the human to act on.
    assert read_sidecar(store, 3).label.status is EpisodeStatus.PENDING_JUDGMENT


def test_attempt_recovery_reads_a_valid_table(tmp_path: Path) -> None:
    """A complete table reads back, proving the honest-recovery check is not vacuous."""
    path = write_valid_parquet(tmp_path / "episode.parquet")
    assert attempt_recovery(path) is True


def test_human_resolves_a_pending_episode(tmp_path: Path) -> None:
    """⑤ Only a human verdict lifts a pending episode to accepted, auto-saved data."""
    store = DatasetStore(root=tmp_path)
    data_path = write_footerless_parquet(tmp_path / "data" / "episode_000004.parquet")
    _, label = recover(store, data_path, episode_index=4)

    resolved = label.with_manual(Verdict.SUCCESS)

    assert resolved.status is EpisodeStatus.JUDGED
    assert resolved.auto_saved is True
    assert resolved.effective_verdict() is Verdict.SUCCESS
    assert resolved.requires_user_judgment() is False
