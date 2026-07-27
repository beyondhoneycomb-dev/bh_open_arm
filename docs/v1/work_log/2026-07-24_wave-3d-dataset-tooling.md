# 2026-07-24 — Wave 3D: dataset tooling (viewer · CoW edit · stats · lineage · integrity · merge · import/export)

> Retrospective record authored 2026-07-27. The five earlier logs (BOOT → Wave −1) stop at
> `2026-07-21`; Waves 3D through 5 were implemented 2026-07-24/25 but never logged
> contemporaneously. This file and the two that follow it close that gap from the commits,
> the auto-memory, and the workflow audit transcripts.

Follows the Wave 3B GUI/sensing/teleop landing (`d38c2e0`). This session built **Wave 3D**,
the dataset-processing band — everything the operator does to a dataset *after* it is
recorded and *before* it trains — over the committed recorder (`WP-3B-11/12`), the frozen
`CTR-REC@v1`, and the Wave 3A synthetic-dataset fixture. The whole band is AI-offline: no
robot, no CAN, no cameras. `lerobot 0.6.0` supplies the edit ops and `compute_stats`.

## What landed

| commit | WPs | what |
|---|---|---|
| `156f818` | WP-3D-01/02/03/04 | viewer, CoW edit + sidecar remap, statistics, reverse-lineage DB |
| `c75c807` | WP-3D-05/06/07 | integrity verifier, merge/split, import/export block |

Built in two dependency-ordered batches (a fan-out of 4 then 3 parallel implementers +
one adversarial auditor each). The one real intra-band edge — WP-3D-06 merge consuming
WP-3D-02 edit — put edit in batch 1 and merge in batch 2, so merge imports the *committed,
audited* CoW module instead of racing an uncommitted sibling. Batch 1 = 116 tests, batch 2
= 99.

## Why — the load-bearing dataset invariants

- **CoW, not in-place.** LeRobot's `modify_tasks` edits in place (destructive). WP-3D-02
  adopts `FR-DAT-022 = copy-on-write` (original immutable), and on an episode-index
  renumber it remaps every sidecar by a **100% content-hash cross-check** — no sampling. A
  mismatch makes the output INVALID and aborts. A remap-less edit is the FAIL_BLOCKING case
  (a label sticks to the wrong episode). The 8 lerobot edit ops are **called**, never
  reimplemented.
- **Train-split-only stats.** WP-3D-03 fits normalization on the train split only and
  applies the same stats to val/test/inference; a per-split re-fit is validation leakage and
  is blocked by a static check. Split-local stats are diagnostic only. std-floor violations
  (a stationary `.vel` or non-contact `.torque` with std ≈ 0) are detected and warned.
- **Reverse lineage is ours.** LeRobot restores lineage forward only; WP-3D-04 owns the
  reverse "which checkpoint used this episode" query (SQLite).
- **READY = 100%.** WP-3D-05's integrity verifier is READY only when every required check
  passes; one failure ⇒ INVALID, and INVALID is never handed to a trainer. This is the gate
  `WP-3C-06` (source-delete interlock) consumes.
- **Merge needs shape + gain equality.** 24-vs-8 observation dims = `use_velocity_and_torque`
  diverged ⇒ merge refused; gain-profile-different episodes must not mix (gain drives the
  following-error distribution). Split only on episode boundaries.
- **Import only.** `lerobot_v3.0` one-way import; gr00t / `lerobot_v2.1` export is blocked;
  imported artifacts show their schema diff and cannot merge with native data.

## What the audits caught (the failure mode this band is built to prevent)

Both batches passed an adversarial audit instructed to run the decisive faults itself, not
trust the implementer's report. Each caught a real defect a per-WP green had hidden:

1. **Batch 1 — process-global logging suppression (fixed in the same commit).**
   `tests/wp3d02/support.py` called `logging.disable(logging.CRITICAL)` and never restored
   it. pytest runs `wp3d02` before `wp3d03` alphabetically, so once any CoW test built a
   dataset, `logger.warning(...)` became a no-op for the rest of the interpreter — and
   WP-3D-03's std-floor **WARN** acceptance test then counted 0 warnings vs 16 and failed.
   Each suite passed *in isolation*; only the whole-suite run bit. Fixed by scoping the
   suppression to the build with a `try/finally` restore; the whole suite went green.

2. **Batch 2 — the `EDIT_INVALID` marker was write-only (fixed in the same commit).**
   WP-3D-02's engine and WP-3D-06's merge write `meta/EDIT_INVALID.json` on an aborted
   sidecar cross-check, and their comments claimed this bars the output from training —
   but **nothing read it**. The integrity verifier's six checks never inspected the marker,
   so a structurally-complete aborted output returned READY (the auditor proved it by
   execution). The only thing incidentally saving it was a missing stats hash, which
   vanishes the moment WP-3D-03 re-stamps stats. Fixed by wiring a **seventh required
   integrity check** that fails when the marker is present, importing the marker name from
   `edit.constants` (one definition, shared) — which makes the sentinel load-bearing and
   `merge.py:124`'s claim true. Mutation-verified: removing the check makes the new test
   fail.

## Verification

```bash
.venv/bin/python -m registry.check --all        # GREEN, 0 judged findings, exit 0
.venv/bin/python -m pytest -q                    # whole suite PYTEST_REAL_EXIT=0
.venv/bin/ruff check backend/dataset tests/wp3d*  # clean
```

Both batches: gate green, whole-suite pytest exit 0 (the batch-1 fix re-verified against the
full suite), ruff clean. The dataset trees are `backend/dataset/{viewer,edit,stats,lineage,
integrity,merge,import_export}/**`, each declared EXCLUSIVE in its `02b` WP row.

## Governance note (surfaced, not buried)

WP-3D-02 resolved `FR-DAT-022`'s `[결정필요]` (original-immutable vs destructive-edit) to
**CoW** and flipped the plan's start-guard from `미해소 → 착수 불가` to `해소됨 → 착수 가능`.
CoW is the only safe dataset-edit policy (the plan's own contract cell already leaned CoW),
the planning gate is open, and the implementer adopted it under instruction — but it is a
decision-needed spec item resolved by an implementer, recorded here for human sign-off.

## Follow-ups

1. The whole-suite pytest (`torch`/MuJoCo heavy) OOMs on this dev box when the user's IDEs
   are resident (~50 GiB). Later sessions verified via `pytest --collect-only` + per-band
   runs; the full-suite green is carried from the parent commit. Watch memory when running
   the full suite.
2. WP-3D-05's integrity verifier is consumed by the (later) `WP-3C-06` source-delete
   interlock — verified there.
