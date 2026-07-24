"""Crash/resume drill for the recorder (WP-3C-07, phase-1 AI-offline).

`02b` §7 WP-3C-07: a recording crash — SIGKILL, disk-full, network-cut — must leave a
recoverable dataset, and recovery is **isolate -> recovery attempt -> user judgment**,
never an automatic save. This package is that drill, built on top of the committed
recorder rather than duplicating it:

- it consumes the WP-3B-11 recorder's *output* — `meta/info.json`, the packed data
  parquet, `meta/episodes`, the `videos/*` tree — as files (`layout`), and reuses the
  WP-3B-12 quality band's footerless detection, isolation and pending-judgment label
  (`backend.recorder.quality`) whole;
- `faults` injects the three crashes (the SIGKILL is a real subprocess kill, not a
  hand-truncated file);
- `recovery` adds the three recovery means — truncate a partial episode, drop an
  unmatched video, rebuild `meta/episodes`;
- `journal` restores the session from a crash-surviving record, carrying the *existing*
  stamped `repo_id` through unchanged — it never re-stamps (⑤);
- `choice` presents the save/discard decision and resolves nothing — phase-2 (the human
  verdict) is deferred (Human-judgment); auto-save is zero (③);
- `drill` runs the whole path and returns the evidence;
- `staticcheck` holds the no-re-stamp and no-auto-save invariants in the source itself.
"""

from __future__ import annotations

from backend.crash_recovery.choice import ChoiceOption, RecoveryChoice, present_choice
from backend.crash_recovery.drill import DrillResult, run_drill
from backend.crash_recovery.faults import (
    FaultKind,
    InjectedFault,
    inject_disk_full,
    inject_network_cut,
    inject_sigkill,
)
from backend.crash_recovery.journal import (
    ResumePlan,
    SessionJournal,
    has_double_stamp,
    journal_path,
    read_journal,
    restore_session,
    write_journal,
)
from backend.crash_recovery.recovery import (
    DropVideoResult,
    RebuildResult,
    RecoveryMeans,
    TruncateResult,
    drop_unmatched_video,
    rebuild_episodes_meta,
    truncate_partial_episode,
)
from backend.crash_recovery.staticcheck import (
    AUTO_SAVE_CALLS,
    RESTAMP_CALLS,
    StaticViolation,
    scan_source,
    scan_tree,
)

__all__ = [
    "AUTO_SAVE_CALLS",
    "RESTAMP_CALLS",
    "ChoiceOption",
    "DrillResult",
    "DropVideoResult",
    "FaultKind",
    "InjectedFault",
    "RebuildResult",
    "RecoveryChoice",
    "RecoveryMeans",
    "ResumePlan",
    "SessionJournal",
    "StaticViolation",
    "TruncateResult",
    "drop_unmatched_video",
    "has_double_stamp",
    "inject_disk_full",
    "inject_network_cut",
    "inject_sigkill",
    "journal_path",
    "present_choice",
    "read_journal",
    "rebuild_episodes_meta",
    "restore_session",
    "run_drill",
    "scan_source",
    "scan_tree",
    "truncate_partial_episode",
    "write_journal",
]
