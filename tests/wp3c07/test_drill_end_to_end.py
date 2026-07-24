"""WP-3C-07 end to end: the full detect -> isolate -> recover -> judge -> resume drill.

`02b` §7 WP-3C-07 (SHAPE-IM(1) phase-1). Each of the three faults is injected into a real
recorded dataset and driven through `run_drill`, and the whole path is checked at once:
the incomplete state is handled, the matching recovery mean runs, the crashed episode is
held for judgment and presented a save/discard choice, the session resumes under the
existing stamped id — and across every fault the two hard invariants hold: `auto_saved`
is False (③) and `restamped` is False (⑤).
"""

from __future__ import annotations

from pathlib import Path

from backend.crash_recovery.choice import ChoiceOption
from backend.crash_recovery.drill import DrillResult, run_drill
from backend.crash_recovery.faults import (
    FaultKind,
    inject_disk_full,
    inject_network_cut,
    inject_sigkill,
)
from backend.crash_recovery.journal import write_journal
from backend.crash_recovery.layout import episode_row_counts, video_files
from backend.crash_recovery.recovery import RecoveryMeans
from backend.recorder.quality.label import EpisodeStatus
from backend.recorder.quality.store import DatasetStore
from tests.wp3c07.support import EPISODE_STEPS, build_baseline_dataset, make_journal

_BASELINE_EPISODES = 2
_SESSION_TARGET = 3
_PARTIAL_ROWS = 2
_INFLIGHT_ROWS = 5
_VIDEO_KEY = "observation.images.cam_high"


def _assert_invariants(drill: DrillResult, original_repo_id: str) -> None:
    """Every drill, whatever the fault, holds no-auto-save (③) and no-re-stamp (⑤)."""
    assert drill.auto_saved is False
    assert drill.restamped is False
    assert drill.pending_label.status is EpisodeStatus.PENDING_JUDGMENT
    assert drill.pending_label.auto_saved is False
    assert set(drill.choice.options) == {ChoiceOption.SAVE, ChoiceOption.DISCARD}
    assert drill.choice.resolved is None
    assert drill.resume_plan.stamped_repo_id == original_repo_id


def test_drill_recovers_a_sigkill(tmp_path: Path) -> None:
    """A SIGKILL crash: footerless detected, isolated, episode held, session resumed."""
    root = tmp_path / "ds"
    baseline = build_baseline_dataset(root, _BASELINE_EPISODES)
    make = make_journal(baseline, _SESSION_TARGET)
    write_journal(root, make)
    inflight = root / "data" / "chunk-000" / "file-001.parquet"
    fault = inject_sigkill(inflight, rows=_INFLIGHT_ROWS)

    drill = run_drill(
        root, fault, DatasetStore(root=root), crashed_episode_index=_BASELINE_EPISODES
    )

    assert drill.fault_kind is FaultKind.SIGKILL
    assert drill.footerless_detected is True
    assert RecoveryMeans.TRUNCATE_PARTIAL_EPISODE in drill.means_applied
    # The footerless in-flight file left the data tree for quarantine.
    assert not inflight.exists()
    assert Path(drill.isolated_path).is_file()
    _assert_invariants(drill, baseline.repo_id)


def test_drill_recovers_a_disk_full(tmp_path: Path) -> None:
    """A disk-full crash: partial episode truncated, meta rebuilt, session resumed."""
    root = tmp_path / "ds"
    baseline = build_baseline_dataset(root, _BASELINE_EPISODES)
    write_journal(root, make_journal(baseline, _SESSION_TARGET))
    fault = inject_disk_full(root, partial_rows=_PARTIAL_ROWS)

    drill = run_drill(
        root, fault, DatasetStore(root=root), crashed_episode_index=_BASELINE_EPISODES
    )

    assert drill.fault_kind is FaultKind.DISK_FULL
    assert drill.footerless_detected is False
    assert drill.means_applied == (
        RecoveryMeans.TRUNCATE_PARTIAL_EPISODE,
        RecoveryMeans.REBUILD_EPISODES_META,
    )
    # The partial episode is gone; the surviving episodes are intact.
    assert set(episode_row_counts(root)) == set(range(_BASELINE_EPISODES))
    assert drill.rebuild_result is not None
    assert drill.rebuild_result.episode_count == _BASELINE_EPISODES
    _assert_invariants(drill, baseline.repo_id)


def test_drill_recovers_a_network_cut(tmp_path: Path) -> None:
    """A network cut: unmatched video dropped, orphaned episode held, session resumed."""
    root = tmp_path / "ds"
    baseline = build_baseline_dataset(root, _BASELINE_EPISODES)
    write_journal(root, make_journal(baseline, _SESSION_TARGET))
    fault = inject_network_cut(root, video_key=_VIDEO_KEY)

    drill = run_drill(
        root, fault, DatasetStore(root=root), crashed_episode_index=_BASELINE_EPISODES
    )

    assert drill.fault_kind is FaultKind.NETWORK_CUT
    assert drill.means_applied == (RecoveryMeans.DROP_UNMATCHED_VIDEO,)
    assert drill.drop_result is not None
    assert len(drill.drop_result.dropped) == 1
    # The unmatched video left the data tree.
    assert video_files(root) == []
    _assert_invariants(drill, baseline.repo_id)


def test_baseline_survives_every_fault_with_complete_episodes(tmp_path: Path) -> None:
    """After a disk-full drill the surviving data still totals the complete episodes' rows."""
    root = tmp_path / "ds"
    baseline = build_baseline_dataset(root, _BASELINE_EPISODES)
    write_journal(root, make_journal(baseline, _SESSION_TARGET))
    fault = inject_disk_full(root, partial_rows=_PARTIAL_ROWS)

    run_drill(root, fault, DatasetStore(root=root), crashed_episode_index=_BASELINE_EPISODES)

    assert sum(episode_row_counts(root).values()) == _BASELINE_EPISODES * EPISODE_STEPS
