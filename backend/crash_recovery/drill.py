"""The crash/resume drill orchestrator (WP-3C-07, SHAPE-IM(1) phase-1).

`02b` §7 WP-3C-07: crash recovery is **isolate -> recovery attempt -> user judgment**,
with no auto-save. This module runs that path end to end over an injected fault and the
recorder's on-disk dataset, and returns the evidence one drill produced:

1. detect the incomplete state (a footerless parquet for a SIGKILL);
2. isolate the crash artefact into the recorder band's quarantine;
3. apply the matching recovery mean(s) so the surviving complete episodes stay a valid
   dataset (truncate / drop unmatched video / rebuild `meta/episodes`);
4. hold the crashed episode PENDING_JUDGMENT and present a save/discard choice — never
   auto-saving it (③);
5. restore the session from the journal, carrying the existing stamped `repo_id` through
   unchanged — no re-stamp (⑤).

Detection, isolation and the pending-judgment label are reused from the recorder quality
band (`backend.recorder.quality`), not re-implemented here; this module adds the three
recovery means, the journal resume, and the choice presentation on top.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from backend.crash_recovery.choice import RecoveryChoice, present_choice
from backend.crash_recovery.constants import (
    EPISODE_INDEX_COLUMN,
    PENDING_REASON_DISK_FULL,
    PENDING_REASON_NETWORK_CUT,
    SALVAGE_PARQUET_TEMPLATE,
)
from backend.crash_recovery.faults import FaultKind, InjectedFault
from backend.crash_recovery.journal import ResumePlan, has_double_stamp, restore_session
from backend.crash_recovery.layout import data_parquets
from backend.crash_recovery.recovery import (
    DropVideoResult,
    RebuildResult,
    RecoveryMeans,
    TruncateResult,
    drop_unmatched_video,
    rebuild_episodes_meta,
    truncate_partial_episode,
)
from backend.recorder.quality.crash import RecoveryOutcome, is_footerless_parquet, recover
from backend.recorder.quality.label import EpisodeLabel
from backend.recorder.quality.sidecar import EpisodeSidecar, write_sidecar
from backend.recorder.quality.store import DatasetStore


@dataclass(frozen=True)
class DrillResult:
    """The evidence one crash/resume drill produced.

    Attributes:
        fault_kind: The injected fault.
        footerless_detected: Whether a footerless parquet was detected (SIGKILL path);
            False for faults that leave a readable artefact.
        isolated_path: Where the crash artefact was isolated to.
        means_applied: The recovery means run, in order.
        truncate_result: The truncate outcome, when that means ran.
        drop_result: The drop-unmatched-video outcome, when that means ran.
        rebuild_result: The rebuild-meta outcome, when that means ran.
        pending_label: The crashed episode's PENDING_JUDGMENT label; never auto-saved.
        choice: The save/discard choice presented for the crashed episode.
        resume_plan: The session restored from the journal.
        auto_saved: Always False — the drill never auto-saves the crashed episode (③).
        restamped: Always False — the resume reuses the stamped id, never re-stamps (⑤).
    """

    fault_kind: FaultKind
    footerless_detected: bool
    isolated_path: str
    means_applied: tuple[RecoveryMeans, ...]
    truncate_result: TruncateResult | None
    drop_result: DropVideoResult | None
    rebuild_result: RebuildResult | None
    pending_label: EpisodeLabel
    choice: RecoveryChoice
    resume_plan: ResumePlan
    auto_saved: bool
    restamped: bool


def run_drill(
    root: Path, fault: InjectedFault, store: DatasetStore, crashed_episode_index: int
) -> DrillResult:
    """Run the full detect -> isolate -> recover -> judge -> resume path for one fault.

    Args:
        root: The dataset root of the crashed session, holding the journal.
        fault: The injected fault to recover from.
        store: The recorder band's store (quarantine + sidecar layout).
        crashed_episode_index: The episode the crash affected; for a disk-full the
            fault's own partial index takes precedence.

    Returns:
        (DrillResult) The evidence, with `auto_saved` and `restamped` both False.
    """
    if fault.kind is FaultKind.SIGKILL:
        outcome, label, means, isolated = _recover_sigkill(store, fault, crashed_episode_index)
        truncate_result: TruncateResult | None = None
        drop_result: DropVideoResult | None = None
        rebuild_result: RebuildResult | None = None
        footerless_detected = True
    elif fault.kind is FaultKind.DISK_FULL:
        (
            outcome,
            label,
            means,
            isolated,
            truncate_result,
            rebuild_result,
        ) = _recover_disk_full(root, store, fault, crashed_episode_index)
        drop_result = None
        footerless_detected = False
    else:
        outcome, label, means, isolated, drop_result = _recover_network_cut(
            root, store, crashed_episode_index
        )
        truncate_result = None
        rebuild_result = None
        footerless_detected = False

    choice = present_choice(outcome, label)
    resume_plan = restore_session(root)
    return DrillResult(
        fault_kind=fault.kind,
        footerless_detected=footerless_detected,
        isolated_path=isolated,
        means_applied=means,
        truncate_result=truncate_result,
        drop_result=drop_result,
        rebuild_result=rebuild_result,
        pending_label=label,
        choice=choice,
        resume_plan=resume_plan,
        auto_saved=label.auto_saved,
        restamped=has_double_stamp(resume_plan.stamped_repo_id),
    )


def _recover_sigkill(
    store: DatasetStore, fault: InjectedFault, crashed_episode_index: int
) -> tuple[RecoveryOutcome, EpisodeLabel, tuple[RecoveryMeans, ...], str]:
    """Recover a SIGKILL fault: detect footerless, then isolate + hold for judgment.

    The footerless in-flight parquet cannot be read; isolating it truncates the crashed
    episode from the dataset, leaving the finalised episodes intact. Detection,
    isolation and the pending label are the recorder band's `recover`, reused whole.
    """
    footerless = fault.footerless_parquet
    if footerless is None or not is_footerless_parquet(footerless):
        raise RuntimeError("SIGKILL fault did not leave a detectable footerless parquet")
    outcome, label = recover(store, footerless, crashed_episode_index)
    return outcome, label, (RecoveryMeans.TRUNCATE_PARTIAL_EPISODE,), outcome.quarantine_path


def _recover_disk_full(
    root: Path, store: DatasetStore, fault: InjectedFault, crashed_episode_index: int
) -> tuple[
    RecoveryOutcome,
    EpisodeLabel,
    tuple[RecoveryMeans, ...],
    str,
    TruncateResult,
    RebuildResult,
]:
    """Recover a disk-full fault: salvage + truncate the partial episode, then rebuild meta.

    The partial episode is readable, so its rows are salvaged into quarantine for the
    human's save decision, then truncated from the packed data, then `meta/episodes` is
    rebuilt from the now-clean data so the metadata agrees with it.
    """
    partial_index = (
        fault.partial_episode_index
        if fault.partial_episode_index is not None
        else crashed_episode_index
    )
    salvage_path, salvaged_bytes, recovered = _salvage_partial_episode(root, store, partial_index)
    truncate_result = truncate_partial_episode(root, partial_index)
    rebuild_result = rebuild_episodes_meta(root)

    outcome = RecoveryOutcome(
        recovered=recovered,
        requires_user_judgment=True,
        auto_saved=False,
        salvaged_bytes=salvaged_bytes,
        quarantine_path=str(salvage_path),
        reason=PENDING_REASON_DISK_FULL,
    )
    label = _hold_for_judgment(store, partial_index, PENDING_REASON_DISK_FULL)
    means = (RecoveryMeans.TRUNCATE_PARTIAL_EPISODE, RecoveryMeans.REBUILD_EPISODES_META)
    return outcome, label, means, str(salvage_path), truncate_result, rebuild_result


def _recover_network_cut(
    root: Path, store: DatasetStore, crashed_episode_index: int
) -> tuple[RecoveryOutcome, EpisodeLabel, tuple[RecoveryMeans, ...], str, DropVideoResult]:
    """Recover a network-cut fault: drop the unmatched video, hold its episode for judgment.

    The orphaned video's bytes survived intact; dropping it into quarantine reconciles
    the tree, and the episode it belonged to — which has no data — is held for judgment.
    """
    drop_result = drop_unmatched_video(root, store)
    quarantine = store.quarantine_dir()
    isolated = drop_result.dropped[0] if drop_result.dropped else str(quarantine)
    salvaged_bytes = _isolated_bytes(quarantine, drop_result)
    outcome = RecoveryOutcome(
        recovered=bool(drop_result.dropped),
        requires_user_judgment=True,
        auto_saved=False,
        salvaged_bytes=salvaged_bytes,
        quarantine_path=isolated,
        reason=PENDING_REASON_NETWORK_CUT,
    )
    label = _hold_for_judgment(store, crashed_episode_index, PENDING_REASON_NETWORK_CUT)
    return outcome, label, (RecoveryMeans.DROP_UNMATCHED_VIDEO,), isolated, drop_result


def _hold_for_judgment(store: DatasetStore, episode_index: int, reason: str) -> EpisodeLabel:
    """Write a PENDING_JUDGMENT sidecar for a crashed episode, never auto-saved.

    Reuses the recorder band's `EpisodeLabel.pending_judgment` and sidecar writer so the
    hold is recorded exactly as the footerless path records it (`auto_saved` False, a
    reason mandatory).
    """
    label = EpisodeLabel.pending_judgment(episode_index, reason)
    write_sidecar(store, EpisodeSidecar(episode_index=episode_index, label=label, report=None))
    return label


def _salvage_partial_episode(
    root: Path, store: DatasetStore, episode_index: int
) -> tuple[Path, int, bool]:
    """Copy a readable partial episode's rows into quarantine before truncation.

    Args:
        root: The dataset root.
        store: The store whose quarantine directory receives the salvage.
        episode_index: The partial episode to salvage.

    Returns:
        (tuple[Path, int, bool]) The salvage path, its byte size, and whether any rows
            were read back.
    """
    blocks = []
    for parquet in data_parquets(root):
        table = pq.read_table(parquet)
        mask = pc.equal(table.column(EPISODE_INDEX_COLUMN), episode_index)
        block = table.filter(mask)
        if block.num_rows:
            blocks.append(block)
    quarantine = store.ensure_quarantine_dir()
    salvage_path = quarantine / SALVAGE_PARQUET_TEMPLATE.format(episode_index=episode_index)
    if blocks:
        pq.write_table(pa.concat_tables(blocks), salvage_path)
        return salvage_path, salvage_path.stat().st_size, True
    return salvage_path, 0, False


def _isolated_bytes(quarantine: Path, drop_result: DropVideoResult) -> int:
    """Sum the sizes of the dropped videos now sitting in quarantine."""
    total = 0
    for dropped in drop_result.dropped:
        isolated = quarantine / Path(dropped).name
        if isolated.is_file():
            total += isolated.stat().st_size
    return total
