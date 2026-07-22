"""WP-3B-12 ①② — success/fail is a sidecar (no re-record), auto is a suggestion the human overrides.

`02b` §5.2 WP-3B-12 ①: writing or changing a label must not re-record the parquet/mp4.
②: the automatic judgment is a suggestion, the human verdict overrides it, and both are
kept so a mismatch stays queryable. The negative branch fixes that an abort without a
reason is the FAIL_BLOCKING defect.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.recorder.quality.label import (
    AbortReason,
    EpisodeLabel,
    EpisodeStatus,
    Provenance,
    QualityLabelError,
    Verdict,
)
from backend.recorder.quality.sidecar import (
    EpisodeSidecar,
    SidecarNotFoundError,
    read_sidecar,
    update_label,
    write_sidecar,
)
from backend.recorder.quality.store import DatasetStore


def _dataset_with_data_files(root: Path) -> tuple[DatasetStore, dict[Path, tuple[int, float]]]:
    """Lay out a dataset root with stand-in parquet/mp4 files and snapshot their state."""
    data = root / "data" / "chunk-000"
    videos = root / "videos" / "chunk-000"
    data.mkdir(parents=True)
    videos.mkdir(parents=True)
    parquet = data / "episode_000000.parquet"
    video = videos / "episode_000000.mp4"
    parquet.write_bytes(b"PARQUET-BODY-PAR1")
    video.write_bytes(b"MP4-BODY")
    snapshot = {path: (path.stat().st_size, path.stat().st_mtime_ns) for path in (parquet, video)}
    return DatasetStore(root=root), snapshot


def test_success_fail_written_as_sidecar_does_not_touch_data(tmp_path: Path) -> None:
    """① A success label is a sidecar under meta/quality; the parquet and mp4 are untouched."""
    store, snapshot = _dataset_with_data_files(tmp_path)

    label = EpisodeLabel.suggested(0, Verdict.SUCCESS).with_manual(Verdict.SUCCESS)
    write_sidecar(store, EpisodeSidecar(episode_index=0, label=label, report=None))

    assert store.sidecar_path(0).is_file()
    assert store.sidecar_path(0).is_relative_to(store.quality_dir())
    for path, (size, mtime) in snapshot.items():
        assert path.stat().st_size == size
        assert path.stat().st_mtime_ns == mtime


def test_label_update_rewrites_only_the_sidecar(tmp_path: Path) -> None:
    """① Flipping success -> fail rewrites the sidecar JSON alone, re-recording nothing."""
    store, snapshot = _dataset_with_data_files(tmp_path)
    write_sidecar(
        store,
        EpisodeSidecar(0, EpisodeLabel.suggested(0, Verdict.SUCCESS), None),
    )

    updated = update_label(
        store, 0, EpisodeLabel.suggested(0, Verdict.SUCCESS).with_manual(Verdict.FAIL)
    )

    assert updated.label.effective_verdict() is Verdict.FAIL
    assert read_sidecar(store, 0).label.effective_verdict() is Verdict.FAIL
    for path, (size, mtime) in snapshot.items():
        assert path.stat().st_size == size
        assert path.stat().st_mtime_ns == mtime


def test_manual_overrides_auto_and_both_are_preserved() -> None:
    """② The human verdict governs, the suggestion survives, and the mismatch is queryable."""
    label = EpisodeLabel.suggested(3, Verdict.SUCCESS).with_manual(Verdict.FAIL)

    assert label.effective_verdict() is Verdict.FAIL
    assert label.auto is not None and label.auto.verdict is Verdict.SUCCESS
    assert label.auto.provenance is Provenance.AUTO
    assert label.manual is not None and label.manual.provenance is Provenance.MANUAL
    assert label.is_conflicting()


def test_agreeing_judgments_are_not_flagged_as_conflict() -> None:
    """② A suggestion the human confirms is preserved but not reported as a mismatch."""
    label = EpisodeLabel.suggested(1, Verdict.SUCCESS).with_manual(Verdict.SUCCESS)

    assert not label.is_conflicting()
    assert label.auto is not None and label.manual is not None


def test_both_judgments_survive_a_sidecar_round_trip(tmp_path: Path) -> None:
    """② The auto/manual pair persists across write and read."""
    store = DatasetStore(root=tmp_path)
    label = EpisodeLabel.suggested(2, Verdict.FAIL).with_manual(Verdict.SUCCESS)
    write_sidecar(store, EpisodeSidecar(2, label, None))

    restored = read_sidecar(store, 2).label

    assert restored.auto is not None and restored.auto.verdict is Verdict.FAIL
    assert restored.manual is not None and restored.manual.verdict is Verdict.SUCCESS
    assert restored.is_conflicting()


def test_abort_without_reason_is_rejected() -> None:
    """An unexplained abort is the WP-3B-12 FAIL_BLOCKING defect and cannot be constructed."""
    with pytest.raises(QualityLabelError):
        EpisodeLabel.aborted(0, "")


def test_aborted_episode_is_never_auto_saved() -> None:
    """An aborted episode carries a reason and is not accepted as data."""
    label = EpisodeLabel.aborted(0, AbortReason.DISK_LOW.value)

    assert label.status is EpisodeStatus.ABORTED
    assert label.abort_reason == AbortReason.DISK_LOW.value
    assert label.auto_saved is False


def test_judged_episode_needs_a_verdict() -> None:
    """A JUDGED label with no auto and no manual verdict is invalid."""
    with pytest.raises(QualityLabelError):
        EpisodeLabel(
            episode_index=0,
            status=EpisodeStatus.JUDGED,
            auto=None,
            manual=None,
            abort_reason=None,
            auto_saved=True,
        )


def test_reading_a_missing_sidecar_raises(tmp_path: Path) -> None:
    """Reading a sidecar that was never written is a clear error, not a silent empty."""
    with pytest.raises(SidecarNotFoundError):
        read_sidecar(DatasetStore(root=tmp_path), 9)
