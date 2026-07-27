# 2026-07-25 — Wave 4B + 4C + GUI 13/13 + Wave 5 offline: the offline scope completes

> Retrospective record authored 2026-07-27, from the commits, auto-memory, and audit
> transcripts. Follows `2026-07-25_wave-3c-offline-and-4a-training-inference.md`. This is the
> second half of the 2026-07-25 push; with it, everything the platform can build **without a
> robot, Isaac Sim, or the GPU deploy-targets** is done.

## What landed

| commit | WPs | what |
|---|---|---|
| `98e4a9d` | WP-4B-01 + WP-G-S10 | usable-policy matrix engine (3-axis), /training screen |
| `a44a80a` | WP-4B-02/04 | checkpoint↔dataset compat gate, deploy-target block matrix |
| `25d8365` | (env02 fix) | remove the unsourced jetson_nano×groot 4.6 ceiling |
| `7c33d0c` | WP-4B-03/05 | inference load preflight, contract-regression registration (Wave 4B complete) |
| `dae1b2b` | WP-4C-03/04 | Wilson/Clopper-Pearson success stats, failure-taxonomy phase-1 |
| `ad36bf9` | WP-G-S11 | /inference screen (GUI 12/13) |
| `d7cf14c` | WP-5-02/WP-G-S01 | dashboard (GUI 13/13 complete) |
| `7c82646` | WP-5-04/05/08 | GUI completion audit, WS load test phase-1, security hardening |
| `2482e83` | WP-4C-05/06/07 | condition protocol, checkpoint-selection scorecard, auto-judge phase-1 |

## Why — the load-bearing invariants

- **4B-01 policy matrix:** capability values are read from the installed lerobot config
  classes at runtime (a copied constant lies on upgrade — the static check bites a literal
  `32`). Three axes (policy × observation-config × projection): bimanual-48 × SmolVLA →
  blocked (max 32); switching obs 24→48 auto-removes SmolVLA/pi0/pi05; switching projection
  to `.pos`-only(16) brings them back (proving the 3rd axis is real). Every block carries a
  source.
- **4B-02 compat gate:** shape compared by `names` (order-sensitive); a stats-hash mismatch
  is a BLOCK not a warning; a **separate comparer** from the 4A-04 maker (so a
  canonicalization bug can't cancel on both sides).
- **4B-04 deploy matrix:** `expected_hz` is looked up from the `11 §2.6` table with a source,
  never computed (0 estimated). Per-target IK benches are deferred (this box is not a fleet
  target).
- **4B-03 load preflight:** the left-gripper limit must be the **sign-mirror** of the right,
  not an identical copy (a copy silently clips left-open — a "wrong success," not an error);
  the v2 URDF limits are read once and injected into **both** the follower config and the
  MJCF `jnt_range` **before** `Kinematics()` (mink reads only `jnt_range`; a split = IK and
  send_action on different limits). Runtime injection, no committed files edited.
- **4B-05 contract regression:** registers 4A/4B facts through the Wave 0-Env checker's API
  — never edits the checker file. A tampered lerobot copy blocks deployment; the `0.6.1`
  ghost version appears nowhere.
- **4C-03 success stats:** Wilson is canonical (N=20 → ±21%p, N=50 → ±13.6%p, reproducing the
  spec's arithmetic; the test pins exact bounds so a wrong formula can't pass);
  Clopper-Pearson only on the n∈{0,n} boundary; N<20 → "statistically meaningless" with no
  ranking; single-run two-checkpoint ranking forbidden; every number a self-baseline.
- **4C-04 taxonomy:** 13 tags each backed by a discriminating signal (0 signal-less);
  9 auto-derived from the committed dual log (POLICY_OUT_OF_BOUNDS from requested≠accepted).
- **4C-05/06/07 phase-1:** dual-condition protocol (NOMINAL/PERTURBED same
  checkpoint/trials/criterion; gap derived, no gap-CI); checkpoint scorecard where
  `offline_metrics` is a field but **never** a sort key (robomimic: the best-val-loss policy
  is 50–100% worse), CI-overlap → "undetermined"; a VLM auto-judge whose MODEL labels never
  enter the human-label success canon.
- **S-10/S-11/S-01 screens:** all 창구 (render backend verdicts, own no logic) — S-10 policy
  list runtime-derived, chart keys = MetricsTracker's actual 7; S-11 always-with-CI, no
  `lerobot-eval`, schema-mismatch lock; S-01 the all-backend dashboard, 0 self-computation,
  unavailable≠normal.
- **Wave 5 offline:** WP-5-04 audits the 13-screen app (routes match spec, air-gap, 0
  reconnect buttons, mode = state transition); WP-5-05 the WS load test (camera degrades
  first under saturation, lease-expiry → scheduler auto-hold, no pass threshold set —
  measurement only); WP-5-08 one lease that is **both** the U-4 safety deadman and the
  FR-OPS-091 security token (replay refused, forced-release increments generation).

## What the audits caught (this band's whole point: no green that catches nothing)

1. **S-10 — the resume button bypassed the training gate (fixed, `98e4a9d`).** The
   checkpoint "resume" button emitted the same `create_job` op guarded only by
   `selectedDataset`, never `canStart` — so a user could start training with the degenerate
   3-choice undecided / preflight BLOCKed / VRAM over. The auditor clicked it with the gate
   closed and it emitted a job. Fixed by consolidating both emitters behind one gated helper
   (a second emit is now structurally impossible), disabling the resume button, and
   strengthening the static+runtime checks (which only caught it because they were also
   strengthened — the prior static check asserted "contains one guard," satisfied by the
   *other* emitter). Mutation-verified.

2. **jetson_nano×groot 4.6 was a fabricated ceiling (fixed, `25d8365`).** The WP-4B-04 audit
   found the committed `targets/guards.py` held `INFERENCE_CEILING_HZ[("jetson_nano","groot")]
   = 4.6` — but spec `11 §2.6` has no Jetson Nano row (it was copied from Orin). The module's
   own docstring says the table is "not a guess." A weaker device than Orin at the *same*
   ceiling is especially dangerous (it would allow sync at a rate the Nano can't sustain).
   Removed the entry so the pair falls through to the honest "no measured ceiling" path
   (FR-TRN-004 / NFR-TEL-004). This was in a *different* WP's committed tree, fixed as a
   focused honesty commit.

3. **S-11 — the schema lock leaked a `select_target` frame (fixed, `ad36bf9`).** The lock
   disabled Mode/Task/Takeover but `selectTarget` emitted a command frame without the
   `locked` guard (DeployMatrixView had no `disabled` prop) — contradicting the module's own
   "every control affordance disables" claim. Benign (it only changes the displayed verdict
   cell) but a real inconsistency; fixed + the CG-G-S11a test strengthened to click the
   target button while locked. Mutation-verified.

4. **CI-16 regression on WP-4C-05 → WP-4C-06 (fixed, `2482e83`).** WP-4C-06's committed 입력
   row declares the edge; WP-4C-06 value-joins the condition as a string (no import); and the
   WP-4C-05 implementer, wrongly assuming its only downstream had no modules, omitted the
   `참조근거`. The batch landed the modules that *activate* the edge but not the one-line
   justification that keeps CI-16 green — so `registry.check --all` exited 1. The auditor also
   caught that the WP-4C-07 self-report claimed "exit 0" by temporarily excluding the sibling
   trees via `.git/info/exclude` — a faked green the integrated tree did not have. Fixed by
   adding the value-join `참조근거` to WP-4C-05's row; gate returned to green. **My own slip
   here too:** I twice read a piped `echo "exit=$?"` as the gate's exit when it was `tail`'s —
   caught it, re-checked the real exit code, and only then committed.

## Honest deferrals — everything left needs real hardware/Isaac (re-verification hooks, 0 faked)

- Wave 3C hardware: WP-3C-01/02/03/05 (real cameras/motors).
- Wave 4C real: rollout execution (WP-4C-01), human labeling (WP-4C-02), perturbation
  execution + selection + reference labels (WP-4C-05/06/07 phase-2).
- Wave 4B-04 per-target IK/inference benches (Jetson / RTX-5090 / A6000).
- Wave 5: power-loss recovery (WP-5-06/07), the live cansend CAN-ACL check (no vcan), Isaac
  Tier-2 (WP-5-09~14, needs Isaac Sim + GPU targets), S-09 Isaac toggle (WP-5-03), WP-5-05
  phase-2 real-camera measurement.

## Verification

```bash
.venv/bin/python -m registry.check --all        # GREEN, 0 judged findings, exit 0
.venv/bin/python -m registry.generate.cli --check # 182 files match, exit 0
.venv/bin/python -m pytest --collect-only -q     # exit 0
# per-band pytest + frontend lane (tsc/eslint/vitest, 787 tests at S-01) each landing
```

Final state: HEAD green, GUI 13/13, 19 implementation commits (`156f818`→`2482e83`), the
offline-buildable scope complete. Every batch went through an adversarial audit; four real
defects (plus the Wave-3D two and the GPU-guard one) were caught and fixed, each
mutation- or execution-verified.

## Follow-ups

1. **Verify WP-5-01/S-13's full contract.** S-13 landed as `WP-G-S13` in Wave 3B; the
   Wave-5 `WP-5-01` is its 02c-side dual-ID. Confirm the 3B build satisfies the full
   CG-G-S13 set (VmLck read, 13-item diagnostic bundle, port-map cross-check, error-code
   lookup) or complete it.
2. **The reconcile flow is `ingest.cli` + `generate.cli` (both).** A re-seed bumps
   `spine_ref` and leaves `registry/build/**` stale until `generate.cli` regenerates; run
   both so `generate --check` stays green (build/ is gitignored, so this never affects a
   commit, but keep it clean).
3. Every hardware/Isaac deferral above carries a skip-with-reason + re-verification hook;
   run them when the robot / Jetson / Isaac Sim are present.
