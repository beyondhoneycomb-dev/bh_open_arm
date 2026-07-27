# 2026-07-25 — Wave 3C offline + Wave 4A: the training/inference backend

> Retrospective record authored 2026-07-27, from the commits, auto-memory, and audit
> transcripts. Follows `2026-07-24_wave-3d-dataset-tooling.md`.

This was the first half of a single long push on 2026-07-25 that carried the platform from
the dataset band through the whole training/inference backend. It builds on the committed
Wave 3D dataset backend and the frozen contracts. Everything here is AI-offline: the GPU
(RTX 5080) is available, but there is no robot, so training uses a dummy subprocess and
inference uses a dummy robot + fixture checkpoints.

## What landed

| commit | WPs | what |
|---|---|---|
| `45b4928` | WP-3C-06/07 + WP-G-S08 | source-delete interlock, crash/resume drill phase-1, /datasets screen |
| `fa996e6` | WP-4A-01/02 | training job orchestrator + GPU-exclusive guard, dataset preflight |
| `abf1307` | WP-4A-03/06 | degenerate-channel detector, `.pos` projection selector |
| `c1fba26` | WP-4A-04 | normalization stats contract + stats-hash lineage embed (SHAPE-CF single owner) |
| `ba0ee16` | WP-4A-05 | lineage record (FR-TRN-054 8-element) + bidirectional query |
| `9387285` | WP-4A-07 | inference engine adapter (sync/rtc/remote-gRPC) + param validators |
| `95c0617` | WP-4A-08 | inference runaway detection (4 conditions) + raw/sent dual logging |
| `2d562db` | WP-4A-01 integration | orchestrator PREFLIGHT gate wiring (closes OBS-1) |

Wave 4A has a real dependency chain (02→03→04→05→07→08), so it was built in
dependency-ordered batches. WP-4A-04 is SHAPE-CF (single owner: the stats-hash
canonicalization is a stale axis, so two implementers would split it).

## Why — the load-bearing invariants

- **3C-06 source-delete interlock:** the raw capture source is deleted only when the
  converted dataset certifies READY via the committed WP-3D-05 verifier **and** four
  capture-preservation checks pass (frame count, video length, row count, `capture_ts`
  monotonicity/preservation). Any mismatch ⇒ original preserved + episode flagged. Its
  dependency (WP-3C-02, real cameras) is hardware; the interlock *logic* is pure data
  comparison, so it builds and tests offline on synthetic before/after fixtures.
- **3C-07 crash/resume phase-1:** a *real* SIGKILL produces a genuinely footerless parquet;
  three recovery means (truncate / drop unmatched video / rebuild `meta/episodes`); journal
  restores the stamped `repo_id` **without** calling `stamp_repo_id()` again; **no
  auto-save** (save/discard is presented, never automatic). Phase-2 (human save/discard
  verdict) is deferred.
- **4A-01 subprocess + GPU-exclusive:** the trainer runs as a subprocess (an in-process OOM
  would kill the CAN-owning backend); the GPU guard is deterministic (2nd job on one GPU
  stays QUEUED 100/100); `resume=false` + an existing `output_dir` presents a 3-way choice
  instead of throwing LeRobot's `FileExistsError` raw.
- **4A-02 preflight:** observation config is judged by info.json `names` (the `.torque`
  suffix), never by shape alone; every gate is defined as MUST-BLOCK-on-a-fault-fixture
  (a `names`-order rotation is the silent-failure archetype). A passing gate can't be built
  from a fixture; a detection gate can (§0.5).
- **4A-03 degenerate detector:** a stationary `.vel` (const 0) or non-contact `.torque`
  (near-const) has std ≈ 0; LeRobot's `denom = std + eps` (eps=1e-8) silently amplifies that
  channel's residual noise ~1e6× and dominates the loss — no exception, no trace, just a bad
  policy. σ_min is a **derivation harness**, never a hardcoded value. A capability token
  (`TrainingClearance`) gates training past a 3-way EXCLUDE/MANUAL_STATS/PROCEED choice.
- **4A-06 projection:** `.pos` indices are derived from the `names` strings (never positional
  slicing); the action target is position-only (send_action hardcodes tau=0, so a
  `.vel`/`.torque` action head trains an unexecuted dimension).
- **4A-04 stats hash:** reuses the committed `stats_content_hash` (one canonicalization, not
  two — two would split stale propagation); serving-hash ≠ training-hash ⇒ deployment BLOCK
  + `OA-DAT-002` (FR-TRN-025 wins over FR-DAT-032's warn).
- **4A-05 lineage:** the FR-TRN-054 8-element record, immutable, auto-stale-on-hash-change
  (derived, not a stored flag); composes WP-3D-04's reverse index rather than forking it.
- **4A-07 inference adapter:** the engine **publishes** timestamped targets to a mailbox; the
  committed `ActuationScheduler` is the sole CAN writer. Backend switch resets state but
  keeps the connection (a reconnect calls `set_zero_position()` = zero-point destruction).
  Remote actions_per_chunk has no default (no stale-50 prefill).
- **4A-08 runaway:** 4 independent conditions (clip-ratio, |Δq|, EE-velocity, queue
  starvation) → P8 hold; **dual logging** records both the policy's raw request and the
  gate-passed sent action, so 4C's failure taxonomy can tell "bad policy" from "gate
  clamped." Thresholds are parameters (values deferred to 4C).

## What the audits caught

1. **4A-01 — the GPU share flag punched through the live-robot ban (fixed, `fa996e6`).**
   `is_available` short-circuited `if allow_share: return True` *before* the FR-TRN-072
   active-session check. `allow_share` exists only for the FR-TRN-028 exception
   (co-scheduling two *training* jobs); it also let training land on a GPU driving a **live
   robot** — the exact VRAM/SM contention that jitters the control loop. Dormant on this
   single-GPU host, but a real safety-guard hole. Fixed by making the session check
   unconditional; mutation-verified.

2. **Wave 4A integration — the PREFLIGHT gate was never wired (OBS-1, closed in `2d562db`).**
   The 4A-02 preflight and 4A-03 degenerate gate were proven to bite *when called*, but the
   4A-01 orchestrator's `PREFLIGHT` state was a passthrough — a job could reach RUNNING and
   launch the trainer without ever obtaining a `TrainingClearance`. The audit flagged this as
   a disclosed integration gap (neither WP could fix it — the launcher is 4A-01's EXCLUSIVE
   tree). Once 02–05 were all committed, a dedicated integration wired the launch path:
   `_launch_running` is the **sole** RUNNING-transition site and takes a **required**
   `TrainingClearance` param (RUNNING is structurally unreachable without a token); a static
   no-bypass check bites on 5 injected bypasses; the pre-existing 4A-01 suite passes
   unchanged.

Everything else audited clean, each verified by the auditor's own faults (e.g. the runaway
auditor injected each of the 4 conditions to prove none masks another; the inference auditor
wired the real `FaultInjectionHarness` and confirmed 40 ticks → 40 CAN writes, all
`ACCEPTED_TARGET`, with zero CAN handles in the adapter).

## Honest deferrals (re-verification hooks, never faked)

- 4A-07 remote-gRPC OpenArm end-to-end rollout (`11` §5-Q8 `[미확인]`) — no real robot;
  carried as a `ReVerificationHook(verified=False)`, param-validation + dummy path run.
- 4A-08 runaway thresholds — values derive from 4C's nominal-rollout distribution; exposed as
  parameters with metering only.
- 3C-07 phase-2 human save/discard verdict.

## Verification

```bash
.venv/bin/python -m registry.check --all        # GREEN, exit 0 (each commit)
.venv/bin/python -m pytest --collect-only -q     # exit 0 (integration; full suite OOMs)
# per-band + dataset/training band run together each landing; frontend lane for S-08
```

Gate green throughout; each commit verified with reconcile → gate → the relevant test band +
a full `--collect-only` (the full `torch` suite OOMs under the resident IDEs, so
cross-pollution was checked via the band-together runs + collection).

## Follow-ups

1. Wire the same discipline check when the real training host lands (the orchestrator gate
   is offline-verified against a dummy trainer).
2. 4A-07 remote-gRPC and 4A-08 thresholds re-verify when a robot / 4C rollouts land.
